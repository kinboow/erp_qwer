"""
客户群 AI 对话服务 — 基于字节跳动豆包 API (OpenAI 兼容) 的 Function Calling 架构

每个被监听的客户群维护独立的对话上下文（以 room_id 为 key），
AI 通过工具自主完成：识别报货 → 查询商品 → 补全缺失信息 → 创建待审核订单。
"""

from __future__ import annotations

import base64
import io
import json
import logging
import secrets
import time
from datetime import datetime
from typing import Any, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal

logger = logging.getLogger(__name__)

try:
    from openpyxl import load_workbook
except Exception:
    load_workbook = None

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
MAX_HISTORY_MESSAGES = 80   # 每个群最多保留的对话轮数
MAX_TOOL_ROUNDS = 8         # 单次消息最多连续 tool-call 轮数（防无限循环）
CHAT_API_TIMEOUT = 240      # AI API 超时（秒）

# ---------------------------------------------------------------------------
# 表创建（复用 downstream_support 统一管理）
# ---------------------------------------------------------------------------
def ensure_chat_table(db: Session) -> None:
    from app.services.downstream_support import ensure_downstream_support_tables
    ensure_downstream_support_tables(db)


# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------
CUSTOMER_GROUP_SYSTEM_PROMPT = """你是一个服装行业客户群的智能报货助手机器人，你在一个微信客户群中工作。

## 一、你的职责
1. 监听群里的聊天消息，识别客户的报货（下单）需求
2. 当客户发送报货信息时（包含货号、颜色、尺码、数量等），自动处理下单
3. 如果报货信息不完整（缺少货号、颜色、尺码或数量），主动@客户询问缺失信息
4. 确认信息完整后，调用工具创建待审核订单
5. 判断订单意图（新下单 / 替换旧单 / 追加补充）

## 二、消息格式
- 每条消息前面标注了发送者姓名，格式为 "[发送者姓名] 消息内容"
- 你能看到群里所有客户消息（不含机器人自身的消息、非图片/Excel的文件）
- 消息是实时推送给你的，每收到一条你就会处理一次
- 图片会以 base64 格式提供，表格文件会转为 Markdown 表格
- **撤回消息**：当客户撤回了一条消息，你会收到格式为 "[系统通知] XXX 撤回了一条消息。被撤回的原始内容：..." 的特殊消息
- **员工与客户区分**：系统会在提示词末尾提供本公司员工名单。员工发的消息不是报货，但你仍然可以看到员工消息作为上下文（例如员工在群里确认客户的订单、回复客户问题等）。
  只有非员工（客户）发的消息才可能是报货信息，员工发的消息永远不要当作报货处理。

## 三、报货识别流程（核心，按顺序执行）

你需要完成以下步骤来处理每条可能的报货消息：

### 步骤1：判断消息是否包含报货数据（核心逻辑，必须严格执行）
判断当前消息是否属于报货信息，分三种情况：

- 【确定是报货 → 继续步骤2】消息中明确包含报货数据：具体的货号/款号、产品名称/别名、颜色+尺码+数量
- 【确定不是报货 → 不处理】日常闲聊、打招呼、问候、表情包、闲聊图片、讨论非订单话题
- 【不确定 → 等待后续消息】以下情况你无法确定是否是报货，应先保持沉默（不回复、不调用工具），等待后续消息提供更多上下文：
  - 仅有下单意图词但无具体数据（如"下单""报货""我要下单"）
  - 模糊的产品描述，无法确认是闲聊还是报单
  - 提到了某个款号或产品名称但上下文不清晰是否在下单
  - **客户单独发了一张包含货号/数量的图片，但没有明确说"下单""报货"等**：此时图片可能是报货，也可能只是询问能不能发货、有没有货等。必须等后续消息再判断。
    如果后续消息是"这些今天能送过来吧""有没有货""能发吗"等咨询类问题，说明客户只是在问物流/库存，**整体不是报货，忽略不处理**。
    如果后续消息是"下单""报货""就这些"等确认下单的意思，才按报货处理。

**不确定时的处理规则（极其重要）：**
1. 第一次遇到不确定的消息：保持沉默，不回复、不调用任何工具，等待后续消息
2. 后续消息到达时，结合之前的不确定消息一起重新判断：
   - 如果现在能确定是报货 → 直接继续步骤2解析
   - 如果现在能确定不是报货 → 忽略
   - 如果仍然不确定 → 继续保持沉默
3. **当同一个客户连续 3 条消息都无法判断时**，才用 send_group_message @客户主动询问，例如：“亲 是要报单吗？发一下货号和数量哈~”
4. 不要对每一条模糊消息都主动询问，这样会骚扰客户

### 步骤2：款号匹配（极其重要）
识别客户提到的产品，并匹配到本年产品目录中的标准货号：
- **必须先调用 query_product_catalog 或 query_product_details 查询**，确认客户提到的款号/名称在本年目录中存在
- 客户可能用货号、产品名称、别名/俗称来指代产品，你需要智能匹配
- **尾号简写匹配**：客户经常只说货号的后几位（尾号），你需要匹配到目录中尾号一致的完整款号。
  例如：目录中有"95862"，客户说"862"就是指它；目录中有"82842"，客户说"842"就是指它。
  如果尾号匹配到多个款号，需要询问客户确认具体是哪一个。
- **只有本年产品目录中存在的款号才能下单**，如果客户提到的款号不在目录中，告知客户该款号不存在或无法识别
- 如果客户提到的名称有多个可能的匹配，先询问客户确认

### 步骤3：颜色和尺码匹配
查询到款号后，用 query_product_details 获取该款号的可选颜色列表和可选尺码列表，然后做匹配：
- **颜色智能匹配规则（极其重要）：**
  - 手写简写/俗称/近义词必须智能对应到列表内最接近的标准名
  - 例如："米白"→"奶油白"、"黑"→"黑色"/"奢雅黑"、"花灰"→"花灰色"、"茶"→"茶色"、"藏青色"→"藏青"、"酱紫"→"酱紫色"
  - 判断标准：只要语义上指的是同一种颜色，就应该匹配到列表中对应的标准名称
  - 只有当客户提到的颜色与列表中所有颜色都完全无关时，才视为无效
- **尺码**必须从该款号的可选尺码列表中匹配

### 步骤4：检查报货信息完整性
完整的报货信息需要四个要素：**款号（货号）、颜色、尺码、数量**。
- 全部齐全 → 步骤5
- 缺少任意字段 → 用 send_group_message @客户，明确告知缺少什么（如"请问需要什么颜色和尺码？"）

### 步骤5：创建订单
信息完整后，调用 create_order_review 创建待审核订单，然后用 send_group_message 通知客户"收到"。
- **数据结构**：每个 item = 一个"款号+颜色"组合，sizes 数组包含该颜色下所有尺码和数量
- **合并规则**：同一款号同一颜色的不同尺码必须合并到同一个 item 的 sizes 数组中
  - 例："82761 白色 M 10件 L 5件" → 一个 item，sizes=[{size:"M", qty:10}, {size:"L", qty:5}]
  - 例："82761 白色 M 10件, 82761 黑色 L 5件" → 两个 item（不同颜色）
- **数量必须是具体数字**，qty 必须大于 0，不能为空或为 0
- **"1"的歧义判断（重要）**：客户单独回复"1"或"好的""嗯"等，在上下文中往往是对上一条消息的确认/肯定，
  而不是下单1件。你必须结合上下文判断：如果前一条是疑问句（如"要不要XXX？""确定吗？"），
  回复"1"代表"确认/是的"，不应当作数量处理。只有在明确的报货语境中（如"82761 白色 M 1"）才把1视为数量
- **备注提取**：如果客户消息中包含与订单相关的备注说明（如发货方式、包装要求、加急、不要吊牌、和XXX一起发等），
  提取到 order_remark 字段。备注仅限与订单处理相关的内容，闲聊内容不算备注。
  如果某条备注仅针对特定款号/颜色，放到对应 item 的 remark 字段中。

## 四、名称映射与别名系统（重要）
- 产品目录中每个款号可能有**别名**（alias），客户可能用别名而非款号来指代产品
- 例如：客户说"弯刀裤"，实际对应货号"82761"；说"云朵裤"，对应"95890"
- **你必须通过查询工具来确认映射关系，不能靠猜测**
- query_product_catalog 支持按别名搜索，query_product_details 也会返回别名信息
- 如果同一个名称可能匹配多个款号，必须先询问客户确认

## 五、图片和表格解析注意事项
1. **背面透字过滤**：如果图片中有纸张背面透过来的文字（颜色较浅、方向相反、镜像或模糊的印刷/手写痕迹），请完全忽略这些背面透字，只识别纸张正面清晰可见的内容
2. **手写内容**：手写内容模糊、涂改、无法辨认的货号/颜色/尺码/数量，**不要猜测**，
   必须调用 send_group_message @客户 在群里询问，明确指出哪些部分看不清（如"亲 图片上第2行的数量看不太清，麻烦确认一下~"）
3. **一次消息多商品**：一条消息/图片/表格中可能包含多个商品的报货信息，要全部识别，每个款号+颜色单独一条记录
4. **表格数据**：Excel/表格中的数据要完整提取，注意表头和数据行的对应关系
5. 只提取货号、颜色、尺码、数量、备注信息，**不需要识别客户名、联系人、下单日期等无关信息**

## 六、订单意图判断（极其重要，必须区分以下情况）

### 情况A：替换旧单（replace）— 取消 ERP 中未发货旧单，以新单为准
客户明确要**取消之前已下过的订单（已进入 ERP 系统的），全部作废，以这次新发的为准**，关键词：
- "替换""换单""重新报""之前那个不要了""把昨天的单改一下""这个替换之前的""作废之前的""全部换成这个"
→ 调用 create_order_review 时设置 order_intent="replace"
→ 审核人员审核时会先取消该客户所有未发货订单，再下新单

### 情况B：更正刚发的报货（写错了/发错了）— 作废审核单后重新下
客户只是**更正刚才发的报货内容**（还没审核下单的），关键词：
- "刚才那个写错了""发错了""重新发一下""那张不要了换这个""上面那个不对"
→ 先调用 void_recent_review 作废刚才的审核单，再用 create_order_review 创建新的（order_intent="new"）

### 情况C：修改旧单（modify）— 修改之前报过的单的部分内容
客户想**修改之前报过的单里面的部分信息**（如改颜色、改数量、去掉某一款、加几件），但不是全部取消重来，关键词：
- "之前那个XXX改成YYY""把82761白色改成黑色""上次报的那个数量改一下""帮我把M改成L""那个减2件""多加一个尺码"
→ 调用 create_modify_review 创建待修改审核单，说明要修改的内容

### 区分 replace 和 modify 的标准（极其重要）
- **replace（替换旧单）**：客户要把旧单**全部取消**，以新发的完整报货为准。新报货包含完整的货号+颜色+尺码+数量。
- **modify（修改旧单）**：客户**不取消旧单**，只是要**改其中某些信息**（改颜色、改尺码、改数量、增减某一款）。
- 如果你无法确定客户是要 replace 还是 modify，用 send_group_message @客户 询问：
  "亲 是要把之前的单全部取消重新报呢，还是只改其中某些内容呀？"

### 情况B 与 情况C 的区分
- 情况B 是**刚才几分钟内发错了**（还在待审核中），作废审核单重来
- 情况C 是**之前已经报过并可能已经审核下单了的**，客户回头想改部分内容

### 追加补充（append）
客户说"追加""再加""补几件""加一点" → order_intent="append"

如果没有明确的替换/追加/更正/修改意图，默认为 new。

### 情况D：客户撤回了报单消息
当你收到“[系统通知] XXX 撤回了一条消息”时，需要判断：
1. 查看被撤回的原始内容是否是报单/报货消息
2. 如果是报单消息，并且你之前已经为这条消息创建了待审核订单：
   - 调用 void_recent_review 作废该客户最近的待审核订单
   - **不要在群里发送任何回复**，静默处理即可
3. 如果被撤回的不是报单消息，或者你还没来得及处理该消息，直接忽略不处理

## 七、回复规范（极其重要）
- **绝大多数消息你都不需要回复，也不需要调用任何工具**。只有以下情况才行动：
  1. 识别到新的报货需求 → 查询产品目录/详情 → 创建订单
  2. 报货信息不完整，需要询问缺失字段 → send_group_message 询问
  3. 订单创建成功 → send_group_message 回复确认
  4. 客户撤回了报单消息，且已创建过订单 → void_recent_review 静默作废（不回复）
  5. 客户要修改之前报过的单的部分内容 → create_modify_review 创建待修改审核单 → send_group_message 回复确认
  6. 不确定客户是要替换旧单还是修改旧单 → send_group_message 询问确认
- **不需要回复的情况（直接忽略，不调用任何工具，不输出任何内容）：**
  - 日常闲聊、问候、表情包、与报货无关的对话
  - 客户询问有没有货、库存够不够、什么时候到货、能不能发货等咨询类问题 — 你不是客服，不负责回答这些问题，完全忽略
  - 客户回复了你之前询问的缺失信息（此时你应该继续处理订单，但不需要再次询问或重复确认）
  - 同一个报货任务的后续补充消息，如果前一条消息已经触发了处理流程，不要重复回复
  - 你已经对某条报货信息回复过确认，后续相同内容不要再次回复
  - **不确定是否为报单的消息**（参见步骤1 “不确定” 情况），在连续 3 条未确认之前不要主动询问
  - **任何超出你职责范围的问题**（如价格咨询、售后问题、物流查询、产品介绍等）— 你只负责报货接单，其他一律保持静默，不要调用 send_group_message，不要回复任何内容

## 八、语气和风格（必须遵守）
- **像真人客服一样说话**，不要像机器人。要口语化、自然、简短
- 适当使用语气词，如"哈""呢""啦""噢""好的""嗯"等
- 标点符号不要太正式，可以用~、！等，少用句号
- **订单创建成功后**只需要说类似"收到~""好的收到啦""知道了~"这样的短回复，**不要说"共X个订单"、不要列订单明细、不要总结**
- 询问缺失信息时语气轻松自然，例如"亲 颜色和尺码发一下呢~""这个要什么码呀"
- 不要用"您好""请问""感谢"等过于正式的词，用"亲""哈""呢"代替
- 回复尽量控制在一句话以内，能短则短
"""

# ---------------------------------------------------------------------------
# Tool Definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "create_order_review",
            "description": (
                "当你确认客户要报货且信息完整（货号、颜色、尺码、数量齐全）时，调用此工具创建待审核订单。"
                "每个 item 是一个“款号+颜色”组合，sizes 数组包含该颜色下所有尺码和对应数量。"
                "同一款号同一颜色的不同尺码必须合并到同一个 item 的 sizes 数组中，不要拆分成多个 item。"
                "例如：客户说'82761 白色 M 10件 L 5件' → 一个 item: product_no=82761, color=白色, sizes=[{size:M, qty:10}, {size:L, qty:5}]"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "description": "订单项列表，每个 item 是一个“款号+颜色”组合",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_no": {"type": "string", "description": "货号/款号"},
                                "color": {"type": "string", "description": "颜色"},
                                "sizes": {
                                    "type": "array",
                                    "description": "该颜色下所有尺码和数量",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "size": {"type": "string", "description": "尺码"},
                                            "qty": {"type": "integer", "description": "数量，必须大于0"},
                                        },
                                        "required": ["size", "qty"],
                                    },
                                },
                                "remark": {"type": "string", "description": "备注（可选）"},
                            },
                            "required": ["product_no", "color", "sizes"],
                        },
                    },
                    "order_remark": {
                        "type": "string",
                        "description": "整单备注（可选），客户提到的与订单处理相关的备注说明，如发货方式、包装要求、加急等。仅提取与订单相关的内容，闲聊不算。",
                    },
                    "order_intent": {
                        "type": "string",
                        "enum": ["new", "replace", "append"],
                        "description": "订单意图: new=新下单, replace=替换旧单, append=追加补充。默认 new。",
                    },
                },
                "required": ["items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_product_catalog",
            "description": (
                "查询本年款产品目录（仅包含本年度在售产品），获取可用的货号、产品名称、别名映射。"
                "客户提到的货号、产品名、别名/俗称都可以作为关键词搜索。"
                "只有本年目录中存在的款号才能创建订单，不在目录中的款号不能下单。"
                "可传入关键词搜索，也可留空获取全部产品。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词（货号、产品名称或别名），留空则返回全部目录",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_product_details",
            "description": (
                "查询指定货号的详细信息，包括该款号的可选颜色列表和可选尺码列表。"
                "在创建订单前必须先查询此工具，确认客户提供的颜色和尺码在该款号的可选范围内。"
                "也支持通过别名查询，如传入别名会自动映射到对应的标准货号。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_no": {
                        "type": "string",
                        "description": "货号/款号",
                    },
                },
                "required": ["product_no"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "void_recent_review",
            "description": (
                "作废/撤销当前群最近创建的一条待审核订单。"
                "当客户说刚才那个写错了、发错了、重新发、那张不要了，指的是更正刚刚提交的报货内容（而不是替换 ERP 中已有的旧订单），"
                "你应该先调用此工具作废之前那条审核单，再创建新的正确订单。"
                "可选传入 review_id 指定作废哪条，不传则自动作废当前群最近的一条 pending 审核单。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "review_id": {
                        "type": "integer",
                        "description": "要作废的审核单 ID（可选，不传则自动找最近一条）",
                    },
                    "reason": {
                        "type": "string",
                        "description": "作废原因，如'客户重新发送了正确的报货信息'",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_modify_review",
            "description": (
                "当客户要修改之前已经报过的单（不是全部取消重来，而是改其中部分内容）时调用此工具。"
                "创建一条'待修改'类型的审核单，人工审核员会根据修改说明去 ERP 中手动修改对应订单。"
                "modify_description 要清晰描述客户要修改什么，比如'82761白色改成黑色'、'M码减2件'等。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "modify_description": {
                        "type": "string",
                        "description": "客户要修改的具体内容描述，如'82761 白色改成黑色，M码数量从10改成8'",
                    },
                    "original_items": {
                        "type": "array",
                        "description": "修改涉及的原始款号信息（可选，帮助审核员定位）",
                        "items": {
                            "type": "object",
                            "properties": {
                                "product_no": {"type": "string", "description": "涉及的货号"},
                                "color": {"type": "string", "description": "涉及的颜色（可选）"},
                            },
                        },
                    },
                },
                "required": ["modify_description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_group_message",
            "description": (
                "向当前客户群发送消息。当需要向客户确认信息、询问缺失字段、"
                "回复收到等时调用。设置 at_sender=true 可以 @触发消息的发送者。"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "要发送的消息文本",
                    },
                    "at_sender": {
                        "type": "boolean",
                        "description": "是否@触发消息的发送者",
                        "default": False,
                    },
                },
                "required": ["message"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool Execution
# ---------------------------------------------------------------------------
def _tool_create_order_review(
    db: Session,
    room_id: str,
    sender_id: str,
    sender_name: str,
    customer: Optional[dict[str, Any]],
    instance_id: str,
    args: dict[str, Any],
) -> str:
    """工具: 创建待审核订单"""
    from app.services.downstream_support import ensure_downstream_support_tables
    ensure_downstream_support_tables(db)

    raw_items = args.get("items") or []
    if not raw_items:
        return json.dumps({"ok": False, "error": "items 为空，无法创建订单"}, ensure_ascii=False)

    # 校验并规范化 items：过滤掉 qty<=0 的 size，过滤掉 sizes 为空的 item
    items: list[dict[str, Any]] = []
    for it in raw_items:
        pno = str(it.get("product_no") or "").strip()
        color = str(it.get("color") or "").strip()
        remark = str(it.get("remark") or "").strip()
        sizes = []
        for s in (it.get("sizes") or []):
            size_name = str(s.get("size") or "").strip()
            qty = int(s.get("qty") or 0)
            if size_name and qty > 0:
                sizes.append({"size": size_name, "qty": qty})
        if pno and color and sizes:
            items.append({"product_no": pno, "color": color, "sizes": sizes, "remark": remark})

    if not items:
        return json.dumps({"ok": False, "error": "items 中无有效的尺码数量数据（qty 必须 > 0）"}, ensure_ascii=False)

    order_intent = args.get("order_intent", "new")
    order_remark = str(args.get("order_remark") or "").strip()
    review_uid = f"RV{datetime.now().strftime('%y%m%d')}{secrets.token_hex(2).upper()}"

    # 直接创建审核记录，parse_status=success（AI 已完成解析）
    order_json: dict[str, Any] = {"items": items}
    if order_remark:
        order_json["remark"] = order_remark
    parsed_order_json = json.dumps(order_json, ensure_ascii=False)
    content_summary = "; ".join(
        f"{it['product_no']} {it['color']} " + "/".join(f"{s['size']}x{s['qty']}" for s in it['sizes'])
        for it in items
    )

    result = db.execute(
        text(
            "INSERT INTO downstream_order_reviews ("
            "review_uid, source_type, instance_id, room_id, sender_id, sender_name, "
            "message_type, content_text, parse_status, review_status, "
            "customer_id, customer_name, parsed_order_json, order_intent, operator_name"
            ") VALUES ("
            ":review_uid, 'ai_conversation', :instance_id, :room_id, :sender_id, :sender_name, "
            "'text', :content_text, 'success', 'pending', "
            ":customer_id, :customer_name, :parsed_order_json, :order_intent, '机器人'"
            ")"
        ),
        {
            "review_uid": review_uid,
            "instance_id": instance_id or None,
            "room_id": room_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "content_text": content_summary,
            "customer_id": customer["id"] if customer else None,
            "customer_name": customer.get("customer_name", "") if customer else "",
            "parsed_order_json": parsed_order_json,
            "order_intent": order_intent,
        },
    )
    review_id = result.lastrowid
    db.commit()

    # SSE 通知前端
    try:
        from app.services.review_events import notify_review_change
        notify_review_change("new_review", {"review_id": review_id})
    except Exception:
        pass

    return json.dumps({
        "ok": True,
        "review_id": review_id,
        "review_uid": review_uid,
        "items_count": len(items),
        "order_intent": order_intent,
    }, ensure_ascii=False)


def _tool_void_recent_review(
    db: Session,
    room_id: str,
    args: dict[str, Any],
) -> str:
    """工具: 作废当前群最近的一条待审核订单"""
    review_id = args.get("review_id")
    reason = args.get("reason") or "AI 自动作废（客户更正报货内容）"

    if review_id:
        row = db.execute(
            text("SELECT id, review_uid, review_status FROM downstream_order_reviews WHERE id = :id AND room_id = :room_id"),
            {"id": review_id, "room_id": room_id},
        ).mappings().first()
    else:
        row = db.execute(
            text(
                "SELECT id, review_uid, review_status FROM downstream_order_reviews "
                "WHERE room_id = :room_id AND review_status = 'pending' "
                "ORDER BY id DESC LIMIT 1"
            ),
            {"room_id": room_id},
        ).mappings().first()

    if not row:
        return json.dumps({"ok": False, "error": "未找到可作废的待审核订单"}, ensure_ascii=False)

    if row["review_status"] != "pending":
        return json.dumps({"ok": False, "error": f"该审核单状态为 {row['review_status']}，只能作废 pending 状态的单"}, ensure_ascii=False)

    db.execute(
        text(
            "UPDATE downstream_order_reviews SET review_status = 'voided', review_note = :note, operator_name = '机器人', updated_at = NOW() WHERE id = :id"
        ),
        {"id": row["id"], "note": reason},
    )
    db.commit()

    # SSE 通知前端
    try:
        from app.services.review_events import notify_review_change
        notify_review_change("new_review", {"review_id": row["id"]})
    except Exception:
        pass

    return json.dumps({
        "ok": True,
        "voided_review_id": row["id"],
        "voided_review_uid": row["review_uid"],
    }, ensure_ascii=False)


def _tool_create_modify_review(
    db: Session,
    room_id: str,
    sender_id: str,
    sender_name: str,
    customer: Optional[dict[str, Any]],
    instance_id: str,
    args: dict[str, Any],
) -> str:
    """工具: 创建待修改审核单（客户要修改之前报过的单的部分内容）"""
    from app.services.downstream_support import ensure_downstream_support_tables
    ensure_downstream_support_tables(db)

    modify_desc = str(args.get("modify_description") or "").strip()
    if not modify_desc:
        return json.dumps({"ok": False, "error": "modify_description 不能为空"}, ensure_ascii=False)

    original_items = args.get("original_items") or []
    review_uid = f"RV{datetime.now().strftime('%y%m%d')}{secrets.token_hex(2).upper()}"

    # 将修改信息存入 parsed_order_json
    order_json: dict[str, Any] = {
        "modify_description": modify_desc,
        "original_items": original_items,
    }
    parsed_order_json = json.dumps(order_json, ensure_ascii=False)

    result = db.execute(
        text(
            "INSERT INTO downstream_order_reviews ("
            "review_uid, source_type, instance_id, room_id, sender_id, sender_name, "
            "message_type, content_text, parse_status, review_status, review_type, "
            "customer_id, customer_name, parsed_order_json, order_intent, operator_name"
            ") VALUES ("
            ":review_uid, 'ai_conversation', :instance_id, :room_id, :sender_id, :sender_name, "
            "'text', :content_text, 'success', 'pending', 'modify', "
            ":customer_id, :customer_name, :parsed_order_json, 'modify', '机器人'"
            ")"
        ),
        {
            "review_uid": review_uid,
            "instance_id": instance_id or None,
            "room_id": room_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "content_text": f"[待修改] {modify_desc}",
            "customer_id": customer["id"] if customer else None,
            "customer_name": customer.get("customer_name", "") if customer else "",
            "parsed_order_json": parsed_order_json,
        },
    )
    review_id = result.lastrowid
    db.commit()

    # SSE 通知前端
    try:
        from app.services.review_events import notify_review_change
        notify_review_change("new_review", {"review_id": review_id})
    except Exception:
        pass

    return json.dumps({
        "ok": True,
        "review_id": review_id,
        "review_uid": review_uid,
        "type": "modify",
        "modify_description": modify_desc,
    }, ensure_ascii=False)


def _tool_query_product_catalog(db: Session, args: dict[str, Any]) -> str:
    """工具: 查询产品目录"""
    from app.services.downstream_orders import query_current_year_catalog
    catalog = query_current_year_catalog(db)

    keyword = (args.get("keyword") or "").strip().lower()
    if keyword:
        filtered = []
        for item in catalog:
            pno = (item.get("product_no") or "").lower()
            pname = (item.get("product_name") or "").lower()
            aliases = [a.lower() for a in (item.get("aliases") or [])]
            if keyword in pno or keyword in pname or any(keyword in a for a in aliases):
                filtered.append(item)
        catalog = filtered

    # 限制返回数量避免 token 过长
    if len(catalog) > 50:
        return json.dumps({
            "total": len(catalog),
            "showing": 50,
            "hint": "结果过多，请用更精确的关键词搜索",
            "products": catalog[:50],
        }, ensure_ascii=False)

    return json.dumps({
        "total": len(catalog),
        "products": catalog,
    }, ensure_ascii=False)


def _tool_query_product_details(db: Session, args: dict[str, Any]) -> str:
    """工具: 查询指定货号详情"""
    from app.services.downstream_orders import query_current_year_catalog
    catalog = query_current_year_catalog(db)

    target_pno = (args.get("product_no") or "").strip()
    if not target_pno:
        return json.dumps({"ok": False, "error": "未指定货号"}, ensure_ascii=False)

    # 精确匹配
    for item in catalog:
        if item["product_no"] == target_pno:
            colors = [c.strip() for c in (item.get("color") or "").split(",") if c.strip()]
            sizes = [s.strip() for s in (item.get("spec") or "").split(",") if s.strip()]
            return json.dumps({
                "ok": True,
                "product_no": item["product_no"],
                "product_name": item.get("product_name", ""),
                "aliases": item.get("aliases", []),
                "available_colors": colors,
                "available_sizes": sizes,
            }, ensure_ascii=False)

    # 别名匹配
    for item in catalog:
        if target_pno in (item.get("aliases") or []):
            colors = [c.strip() for c in (item.get("color") or "").split(",") if c.strip()]
            sizes = [s.strip() for s in (item.get("spec") or "").split(",") if s.strip()]
            return json.dumps({
                "ok": True,
                "product_no": item["product_no"],
                "product_name": item.get("product_name", ""),
                "aliases": item.get("aliases", []),
                "matched_via_alias": target_pno,
                "available_colors": colors,
                "available_sizes": sizes,
            }, ensure_ascii=False)

    return json.dumps({"ok": False, "error": f"未找到货号 {target_pno}"}, ensure_ascii=False)


async def _tool_send_group_message(
    room_id: str,
    sender_id: str,
    instance_id: str,
    args: dict[str, Any],
) -> str:
    """工具: 向群里发送消息"""
    from app.services.wechat_reply import send_room_at
    db = SessionLocal()
    try:
        message = args.get("message", "")
        at_sender = args.get("at_sender", False)
        at_list = [sender_id] if at_sender and sender_id else None

        result = await send_room_at(
            db, room_id, message,
            at_list=at_list,
            instance_id=int(instance_id) if instance_id and instance_id.isdigit() else None,
        )
        return json.dumps({"ok": result.get("ok", False)}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 对话历史管理
# ---------------------------------------------------------------------------
def _save_message(db: Session, room_id: str, role: str, content: Any = None,
                  name: str = None, tool_calls: Any = None, tool_call_id: str = None) -> None:
    """保存一条对话消息到 DB"""
    ensure_chat_table(db)
    content_str = json.dumps(content, ensure_ascii=False) if isinstance(content, (list, dict)) else content
    tool_calls_str = json.dumps(tool_calls, ensure_ascii=False) if tool_calls else None
    db.execute(
        text(
            "INSERT INTO ai_chat_messages (room_id, role, content, name, tool_calls, tool_call_id) "
            "VALUES (:room_id, :role, :content, :name, :tool_calls, :tool_call_id)"
        ),
        {
            "room_id": room_id,
            "role": role,
            "content": content_str,
            "name": name,
            "tool_calls": tool_calls_str,
            "tool_call_id": tool_call_id,
        },
    )
    db.commit()


def _load_history(db: Session, room_id: str, limit: int = MAX_HISTORY_MESSAGES) -> list[dict[str, Any]]:
    """加载该群的最近 N 条对话历史，组装为 OpenAI messages 格式"""
    ensure_chat_table(db)
    rows = db.execute(
        text(
            "SELECT role, content, name, tool_calls, tool_call_id "
            "FROM ai_chat_messages "
            "WHERE room_id = :room_id "
            "ORDER BY id DESC LIMIT :limit"
        ),
        {"room_id": room_id, "limit": limit},
    ).mappings().all()

    messages: list[dict[str, Any]] = []
    for r in reversed(rows):  # 恢复时间正序
        msg: dict[str, Any] = {"role": r["role"]}
        content = r["content"]

        # 尝试解析 JSON content（multimodal）
        if content and content.startswith("["):
            try:
                msg["content"] = json.loads(content)
            except Exception:
                msg["content"] = content
        else:
            msg["content"] = content

        if r["name"]:
            msg["name"] = r["name"]
        if r["tool_calls"]:
            try:
                msg["tool_calls"] = json.loads(r["tool_calls"]) if isinstance(r["tool_calls"], str) else r["tool_calls"]
            except Exception:
                pass
        if r["tool_call_id"]:
            msg["tool_call_id"] = r["tool_call_id"]

        messages.append(msg)

    return messages


def _trim_history(db: Session, room_id: str, keep: int = MAX_HISTORY_MESSAGES) -> None:
    """清理超出保留数量的旧消息"""
    try:
        db.execute(
            text(
                "DELETE FROM ai_chat_messages "
                "WHERE room_id = :room_id AND id NOT IN ("
                "  SELECT id FROM (SELECT id FROM ai_chat_messages WHERE room_id = :room_id ORDER BY id DESC LIMIT :keep) t"
                ")"
            ),
            {"room_id": room_id, "keep": keep},
        )
        db.commit()
    except Exception as exc:
        logger.debug("清理对话历史异常: %s", exc)


# ---------------------------------------------------------------------------
# CDN 附件下载
# ---------------------------------------------------------------------------
async def _cdn_download_once(
    runtime: dict[str, Any],
    cdn_params: dict[str, Any],
    save_path: "Path",
) -> str:
    """单次 CDN 下载尝试，成功返回 base64，失败抛异常。"""
    from pathlib import Path as _Path

    mode = cdn_params.get("mode", "wx_download")
    api_route = f"cdn/{mode}"
    body = {k: v for k, v in cdn_params.items() if k != "mode"}
    body["save_path"] = str(save_path)

    headers: dict[str, str] = {}
    if runtime.get("api_key"):
        headers["X-API-Key"] = runtime["api_key"]

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{runtime['api_base_url']}/api/{runtime['wxid']}/{api_route}",
            json=body,
            headers=headers,
        )
        resp.raise_for_status()
        resp_data = resp.json()

    if isinstance(resp_data, dict) and resp_data.get("code") not in (0, None):
        raise RuntimeError(resp_data.get("msg") or "CDN API 返回错误")

    actual_path = save_path
    if not actual_path.is_file():
        data_body = resp_data.get("data") if isinstance(resp_data.get("data"), dict) else {}
        for key in ("save_path", "path", "file_path"):
            possible = str(data_body.get(key) or "").strip()
            if possible and _Path(possible).is_file():
                actual_path = _Path(possible)
                break
    if not actual_path.is_file():
        raise RuntimeError("下载后文件不存在")

    file_bytes = actual_path.read_bytes()
    try:
        actual_path.unlink(missing_ok=True)
    except Exception:
        pass
    return base64.b64encode(file_bytes).decode("ascii")


async def _download_attachment_from_cdn(
    db: Session,
    payload: dict[str, Any],
    instance_id: str,
    message_type: str,
    *,
    room_id: str = "",
    room_name: str = "",
    file_name: str = "",
) -> str:
    """从企微 CDN 下载附件，带重试与备用模式，返回 base64。

    重试策略：
      1) 首选模式 × 1 次
      2) 同模式重试 × 1 次
      3) 备用模式 × 2 次（如果 payload 中有两种 CDN 参数）
    全部失败后向通知群发送告警。
    """
    from pathlib import Path
    from app.services.media_archive import _extract_all_cdn_candidates, _resolve_runtime, _guess_extension
    import asyncio as _asyncio

    candidates = _extract_all_cdn_candidates(payload)
    if not candidates:
        logger.debug("CDN下载: 无CDN参数，跳过")
        return ""

    runtime = _resolve_runtime(db, instance_id)
    if not runtime.get("api_base_url") or not runtime.get("wxid"):
        logger.debug("CDN下载: 缺少运行时配置")
        return ""

    ext = _guess_extension(file_name or "", message_type)
    download_dir = Path(__file__).resolve().parents[2] / "temp" / "ai_chat_attachments"
    download_dir.mkdir(parents=True, exist_ok=True)

    # 构建尝试队列：首选模式 × 2 + 备用模式 × 2
    primary = candidates[0]
    alternate = candidates[1] if len(candidates) > 1 else None
    attempts: list[tuple[str, dict[str, Any]]] = [
        (f"首选({primary.get('mode')})", primary),
        (f"重试({primary.get('mode')})", primary),
    ]
    if alternate:
        attempts.append((f"备用({alternate.get('mode')})-1", alternate))
        attempts.append((f"备用({alternate.get('mode')})-2", alternate))

    last_err = ""
    for label, params in attempts:
        save_path = download_dir / f"chat_{secrets.token_hex(4)}{ext}"
        try:
            result_b64 = await _cdn_download_once(runtime, params, save_path)
            logger.info("CDN下载成功 [%s]: %d bytes", label, len(result_b64) * 3 // 4)
            return result_b64
        except Exception as exc:
            last_err = str(exc)
            logger.warning("CDN下载失败 [%s]: %s", label, exc)
            await _asyncio.sleep(1)

    # 全部失败 → 通知群告警
    display_name = file_name or ("图片" if message_type in ("image", "img", "picture") else "文件")
    display_room = room_name or room_id or "未知群"
    alert_msg = f"⚠️ 客户群文件下载失败\n群聊：{display_room}\n文件：{display_name}\n原因：{last_err}\n已重试 {len(attempts)} 次均失败，请人工处理。"
    try:
        await _notify_download_failure(db, alert_msg)
    except Exception as notify_exc:
        logger.warning("下载失败通知发送异常: %s", notify_exc)

    return ""


async def _notify_download_failure(db: Session, message: str) -> None:
    """向所有通知群发送下载失败告警。"""
    from app.services.wechat_reply import send_room_at
    try:
        rows = db.execute(
            text("SELECT room_id FROM downstream_customer_wechat_rooms WHERE room_type = 'notification'")
        ).mappings().all()
    except Exception:
        rows = []
    for row in rows:
        try:
            await send_room_at(db, row["room_id"], message)
        except Exception as exc:
            logger.warning("通知群推送失败 room=%s: %s", row["room_id"], exc)


# ---------------------------------------------------------------------------
# Excel → Markdown 转换 (复用)
# ---------------------------------------------------------------------------
def _excel_to_markdown(attachment_base64: str) -> str:
    """将 Excel 附件转为 Markdown 表格"""
    if not attachment_base64 or load_workbook is None:
        return ""
    try:
        binary = base64.b64decode(attachment_base64)
        workbook = load_workbook(io.BytesIO(binary), data_only=True)
    except Exception as exc:
        return f"Excel 解析失败: {exc}"
    parts: list[str] = []
    for sheet in workbook.worksheets[:3]:
        parts.append(f"## Sheet: {sheet.title}\n")
        rows_data: list[list[str]] = []
        for row in sheet.iter_rows(min_row=1, max_row=50, values_only=True):
            row_values = ["" if c is None else str(c).strip() for c in row[:20]]
            if any(row_values):
                rows_data.append(row_values)
        if not rows_data:
            parts.append("（空表）\n")
            continue
        max_cols = max(len(r) for r in rows_data)
        for r in rows_data:
            while len(r) < max_cols:
                r.append("")
        header = rows_data[0]
        parts.append("| " + " | ".join(h or " " for h in header) + " |")
        parts.append("| " + " | ".join("---" for _ in header) + " |")
        for data_row in rows_data[1:]:
            parts.append("| " + " | ".join(data_row) + " |")
        parts.append("")
    return "\n".join(parts).strip()


# ---------------------------------------------------------------------------
# 消息批次窗口：同一个群 35 秒内的消息合并后统一送 AI
# ---------------------------------------------------------------------------
import asyncio as _asyncio

BATCH_WINDOW_SECONDS = 22  # 批次等待窗口

# room_id → {"task": asyncio.Task, "trigger_ts": float, "count": int,
#             "customer": dict|None, "instance_id": str, "senders": dict}
_room_batches: dict[str, dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# 动态 System Prompt（注入员工名单）
# ---------------------------------------------------------------------------
_employee_cache: dict[str, Any] = {"names": [], "ts": 0.0}

def _build_system_prompt(db: Session) -> str:
    """在静态 prompt 基础上追加本公司员工名单，缓存 5 分钟。"""
    import time as _t
    now = _t.time()
    if now - _employee_cache["ts"] > 300 or not _employee_cache["names"]:
        try:
            rows = db.execute(
                text("SELECT nickname FROM wechat_employee_accounts WHERE nickname != '' ORDER BY id")
            ).fetchall()
            _employee_cache["names"] = [r[0] for r in rows if r[0]]
        except Exception:
            _employee_cache["names"] = []
        _employee_cache["ts"] = now

    names = _employee_cache["names"]
    if not names:
        return CUSTOMER_GROUP_SYSTEM_PROMPT

    employee_section = "\n\n## 附录：本公司员工名单\n以下是本公司员工在群里的昵称，这些人发的消息不是报货，仅作为上下文参考：\n"
    employee_section += "、".join(names)
    return CUSTOMER_GROUP_SYSTEM_PROMPT + employee_section


# ---------------------------------------------------------------------------
# 核心：处理客户群消息
# ---------------------------------------------------------------------------
async def process_customer_group_message(
    db: Session,
    *,
    room_id: str,
    sender_id: str,
    sender_name: str,
    message_type: str,
    content_text: str,
    attachment_base64: str = "",
    file_name: str = "",
    customer: Optional[dict[str, Any]] = None,
    instance_id: str = "",
    bot_wxid: str = "",
    payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """处理来自客户群的一条消息：先保存到对话历史，再通过 35 秒批次窗口统一送 AI。

    返回: {"ok": True/False, "batched": bool, ...}
    """
    ensure_chat_table(db)

    # ---- 0. 图片/文件缺失 base64 时尝试从 CDN 下载 ----
    is_media = message_type in ("image", "img", "picture", "file")
    if is_media and not attachment_base64 and payload:
        room_name_display = (customer or {}).get("room_name") or room_id
        logger.info("图片/文件缺 base64，尝试 CDN 下载: room=%s type=%s", room_id, message_type)
        attachment_base64 = await _download_attachment_from_cdn(
            db, payload, instance_id, message_type,
            room_id=room_id, room_name=room_name_display, file_name=file_name,
        )

    # ---- 1. 构建 user message content ----
    prefix = f"[{sender_name or sender_id}] "
    user_content: Any  # str 或 list (multimodal)

    if message_type in ("image", "img", "picture") and attachment_base64:
        user_content = [
            {"type": "text", "text": prefix + (content_text or "（发送了一张图片）")},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{attachment_base64}"}},
        ]
    elif message_type == "file" and file_name.lower().endswith((".xlsx", ".xls")) and attachment_base64:
        md_table = _excel_to_markdown(attachment_base64)
        if md_table:
            user_content = prefix + f"（发送了表格文件 {file_name}）\n\n{md_table}"
        else:
            user_content = prefix + f"（发送了文件 {file_name}，无法解析）"
    else:
        user_content = prefix + (content_text or "")

    # ---- 2. 立即保存 user message 到对话历史 ----
    _save_message(db, room_id, "user", content=user_content, name=sender_name)
    logger.info("消息已入库: room=%s sender=%s type=%s", room_id, sender_name, message_type)

    # ---- 2.5 熔断期间缓冲消息信息（消息仍入库，只是不送AI） ----
    from app.services.ai_circuit_breaker import is_tripped as _cb_is_tripped, buffer_message as _cb_buffer
    if _cb_is_tripped():
        _cb_buffer({
            "room_id": room_id,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "customer_name": (customer or {}).get("customer_name", ""),
            "content_preview": (content_text or "")[:200],
            "message_type": message_type,
        })

    # ---- 3. 批次窗口：35 秒内同群消息合并后统一送 AI ----
    batch = _room_batches.get(room_id)

    if batch:
        # 批次已在进行中 — 追加计数，刷新发送者信息，跳过 AI
        batch["count"] += 1
        batch["senders"][sender_id] = sender_name
        if customer:
            batch["customer"] = customer
        if instance_id:
            batch["instance_id"] = instance_id
        logger.info("消息加入批次窗口: room=%s count=%d 剩余 %.0fs",
                    room_id, batch["count"],
                    max(0, batch["trigger_ts"] + BATCH_WINDOW_SECONDS - time.time()))
        return {"ok": True, "batched": True, "batch_count": batch["count"]}

    # 无活跃批次 — 此消息为触发消息，创建新批次
    batch_info: dict[str, Any] = {
        "trigger_ts": time.time(),
        "count": 1,
        "customer": dict(customer) if customer else None,
        "instance_id": instance_id or "",
        "senders": {sender_id: sender_name},
        "task": None,
    }
    _room_batches[room_id] = batch_info

    # 启动延迟任务
    task = _asyncio.create_task(_batch_delayed_ai_call(room_id, batch_info))
    batch_info["task"] = task

    logger.info("批次窗口开启: room=%s 等待 %ds", room_id, BATCH_WINDOW_SECONDS)
    return {"ok": True, "batched": True, "batch_trigger": True}


async def _batch_delayed_ai_call(room_id: str, batch_info: dict[str, Any]) -> None:
    """等待批次窗口结束后，加载完整历史并统一调用 AI。"""
    try:
        await _asyncio.sleep(BATCH_WINDOW_SECONDS)
    except _asyncio.CancelledError:
        logger.info("批次任务被取消: room=%s", room_id)
        return
    finally:
        _room_batches.pop(room_id, None)

    msg_count = batch_info.get("count", 0)
    customer = batch_info.get("customer")
    instance_id = batch_info.get("instance_id", "")
    senders = batch_info.get("senders", {})
    # 取最后一个发送者作为 sender_id / sender_name（工具调用可能需要）
    last_sender_id = list(senders.keys())[-1] if senders else ""
    last_sender_name = senders.get(last_sender_id, "")

    logger.info("批次窗口到期，开始 AI 处理: room=%s 共 %d 条消息", room_id, msg_count)

    # 熔断检查：如果 AI 已暂停，缓冲消息而不调用
    from app.services.ai_circuit_breaker import is_tripped, buffer_message
    if is_tripped():
        logger.warning("[AI熔断] 批次窗口到期但 AI 已暂停，缓冲消息: room=%s count=%d", room_id, msg_count)
        buffer_message({
            "room_id": room_id,
            "sender_id": last_sender_id,
            "sender_name": last_sender_name,
            "customer_name": (customer or {}).get("customer_name", ""),
            "content_preview": f"[批次 {msg_count} 条消息]",
            "message_type": "batch",
        })
        return

    # 获取同群锁 + 全局信号量，与 _send_msg_to_ai 共享，避免并发冲突
    from app.services.wechat_runtime_compat import _get_room_lock, _get_ai_semaphore
    room_lock = _get_room_lock(room_id)
    async with room_lock:
        async with _get_ai_semaphore():
            db = SessionLocal()
            try:
                await _run_ai_on_history(
                    db,
                    room_id=room_id,
                    sender_id=last_sender_id,
                    sender_name=last_sender_name,
                    customer=customer,
                    instance_id=instance_id,
                )
            except Exception as exc:
                logger.error("批次 AI 处理异常: room=%s err=%s", room_id, exc, exc_info=True)
            finally:
                db.close()


async def _run_ai_on_history(
    db: Session,
    *,
    room_id: str,
    sender_id: str,
    sender_name: str,
    customer: Optional[dict[str, Any]],
    instance_id: str,
) -> dict[str, Any]:
    """加载对话历史并调用 AI（多轮 tool-call），用于批次窗口到期后的统一处理。"""

    # ---- 1. 加载对话历史 ----
    history = _load_history(db, room_id)

    # ---- 2. 组装 API messages (system + history) ----
    system_prompt = _build_system_prompt(db)
    api_messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    for i, msg in enumerate(history):
        if isinstance(msg.get("content"), list) and i < len(history) - 5:
            text_parts = [p.get("text", "") for p in msg["content"] if p.get("type") == "text"]
            api_messages.append({"role": msg["role"], "content": " ".join(text_parts) + " [图片已省略]"})
        else:
            api_messages.append(msg)

    # ---- 3. 调用 AI (可能多轮 tool call) ----
    from app.services.ai_circuit_breaker import is_tripped, record_success, record_error
    if is_tripped():
        logger.warning("AI 已熔断，跳过对话: room=%s", room_id)
        return {"ok": False, "reason": "ai_tripped"}

    cfg = _load_ai_config(db)
    if not cfg.get("enabled"):
        logger.info("AI 已关闭，跳过对话: room=%s", room_id)
        return {"ok": False, "reason": "ai_disabled"}

    tool_round = 0
    ai_responded = False

    while tool_round < MAX_TOOL_ROUNDS:
        tool_round += 1
        try:
            ai_response = await _call_chat_api(cfg, api_messages)
            record_success()
        except Exception as exc:
            logger.error("AI API 调用失败: room=%s err=%s", room_id, exc)
            await record_error(str(exc))
            break

        choice = (ai_response.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        ai_content = message.get("content")
        tool_calls = message.get("tool_calls")

        # 保存 assistant 消息
        _save_message(db, room_id, "assistant", content=ai_content, tool_calls=tool_calls)
        api_messages.append(message)

        if not tool_calls:
            if ai_content and ai_content.strip():
                ai_responded = True
                logger.info("AI 文本回复 (无工具调用): room=%s content=%s",
                            room_id, (ai_content or "")[:200])
            break

        # ---- 执行工具调用 ----
        for tc in tool_calls:
            func_name = tc.get("function", {}).get("name", "")
            func_args_str = tc.get("function", {}).get("arguments", "{}")
            call_id = tc.get("id", "")

            try:
                func_args = json.loads(func_args_str)
            except Exception:
                func_args = {}

            logger.info("AI 工具调用: room=%s tool=%s args=%s", room_id, func_name, func_args_str[:500])

            tool_result = await _execute_tool(
                func_name, func_args,
                db=db, room_id=room_id, sender_id=sender_id,
                sender_name=sender_name, customer=customer,
                instance_id=instance_id,
            )

            _save_message(db, room_id, "tool", content=tool_result, name=func_name, tool_call_id=call_id)
            api_messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": tool_result,
            })
            ai_responded = True

    # ---- 清理旧消息 ----
    _trim_history(db, room_id)

    return {"ok": True, "ai_responded": ai_responded}


# ---------------------------------------------------------------------------
# AI API 调用
# ---------------------------------------------------------------------------
def _load_ai_config(db: Optional[Session] = None) -> dict[str, Any]:
    """加载 AI 配置（复用 ai_config 服务）"""
    if db is not None:
        try:
            from app.services.ai_config import get_ai_config_for_parser
            return get_ai_config_for_parser(db)
        except Exception as exc:
            logger.warning("加载 AI 配置失败: %s", exc)
    return {
        "provider": "qwen",
        "base_url": settings.OPENAI_BASE_URL.rstrip("/"),
        "api_key": settings.OPENAI_API_KEY,
        "model": settings.OPENAI_MODEL,
        "vision_model": settings.OPENAI_VISION_MODEL,
        "temperature": 0.1,
        "enabled": True,
    }


def _messages_contain_image(messages: list[dict[str, Any]]) -> bool:
    """检测 messages 中是否包含图片内容"""
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if part.get("type") == "image_url":
                    return True
    return False


async def _call_chat_api(cfg: dict[str, Any], messages: list[dict[str, Any]]) -> dict[str, Any]:
    """调用 AI Chat Completions API (含 tools)"""
    base_url = cfg["base_url"].rstrip("/")
    api_key = cfg["api_key"]
    provider = cfg.get("provider", "qwen")

    # 有图片时用 vision 模型
    model = cfg["vision_model"] if _messages_contain_image(messages) else cfg["model"]

    request_body: dict[str, Any] = {
        "model": model,
        "temperature": cfg.get("temperature", 0.1),
        "messages": messages,
        "tools": TOOL_DEFINITIONS,
        "tool_choice": "auto",
        "max_tokens": 16384,
    }
    # 按供应商开启深度思考
    if provider == "qwen":
        request_body["enable_thinking"] = True
    elif provider == "bytedance":
        request_body["thinking"] = {"type": "enabled"}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    # 深度思考需要更长超时
    timeout = CHAT_API_TIMEOUT if provider != "bytedance" else max(CHAT_API_TIMEOUT, 300)
    t0 = time.time()
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=request_body,
        )
    duration_ms = int((time.time() - t0) * 1000)

    if response.status_code >= 400:
        logger.error("AI Chat API 错误: status=%d body=%s", response.status_code, response.text[:1000])
    response.raise_for_status()

    payload = response.json()
    usage = payload.get("usage") or {}
    logger.info("AI Chat API: model=%s tokens=%s/%s/%s duration=%dms",
                model,
                usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens"),
                duration_ms)

    # 记录日志
    try:
        db = SessionLocal()
        try:
            from app.services.ai_config import log_ai_call
            choice = (payload.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            log_ai_call(
                db,
                model=model,
                caller="ai_chat_service",
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                duration_ms=duration_ms,
                status="success",
                response_summary=(msg.get("content") or "")[:4000],
            )
        finally:
            db.close()
    except Exception:
        pass

    return payload


async def _execute_tool(
    name: str,
    args: dict[str, Any],
    *,
    db: Session,
    room_id: str,
    sender_id: str,
    sender_name: str,
    customer: Optional[dict[str, Any]],
    instance_id: str,
) -> str:
    """分发并执行工具调用，返回结果字符串"""
    try:
        if name == "create_order_review":
            return _tool_create_order_review(
                db, room_id, sender_id, sender_name, customer, instance_id, args,
            )
        elif name == "create_modify_review":
            return _tool_create_modify_review(
                db, room_id, sender_id, sender_name, customer, instance_id, args,
            )
        elif name == "void_recent_review":
            return _tool_void_recent_review(db, room_id, args)
        elif name == "query_product_catalog":
            return _tool_query_product_catalog(db, args)
        elif name == "query_product_details":
            return _tool_query_product_details(db, args)
        elif name == "send_group_message":
            return await _tool_send_group_message(room_id, sender_id, instance_id, args)
        else:
            return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
    except Exception as exc:
        logger.error("工具执行失败: tool=%s err=%s", name, exc)
        return json.dumps({"error": f"工具执行异常: {exc}"}, ensure_ascii=False)
