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
- 你能看到群里所有客户消息（不含机器人自身、员工的消息、非图片/Excel的文件）
- 消息是实时推送给你的，每收到一条你就会处理一次
- 图片会以 base64 格式提供，表格文件会转为 Markdown 表格
- **撤回消息**：当客户撤回了一条消息，你会收到格式为 “[系统通知] XXX 撤回了一条消息。被撤回的原始内容：...” 的特殊消息

## 三、报货识别流程（核心，按顺序执行）

你需要完成以下步骤来处理每条可能的报货消息：

### 步骤1：判断消息是否包含报货数据（核心逻辑，必须严格执行）
判断当前消息是否属于报货信息，分三种情况：

- 【确定是报货 → 继续步骤2】消息中明确包含报货数据：具体的货号/款号、产品名称/别名、颜色+尺码+数量
- 【确定不是报货 → 不处理】日常闲聊、打招呼、问候、表情包、闲聊图片、讨论非订单话题
- 【不确定 → 等待后续消息】以下情况你无法确定是否是报货，应先保持沉默（不回复、不调用工具），等待后续消息提供更多上下文：
  - 仅有下单意图词但无具体数据（如“下单”“报货”“我要下单”）
  - 模糊的产品描述，无法确认是闲聊还是报单
  - 提到了某个款号或产品名称但上下文不清晰是否在下单

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

## 四、名称映射与别名系统（重要）
- 产品目录中每个款号可能有**别名**（alias），客户可能用别名而非款号来指代产品
- 例如：客户说"弯刀裤"，实际对应货号"82761"；说"云朵裤"，对应"95890"
- **你必须通过查询工具来确认映射关系，不能靠猜测**
- query_product_catalog 支持按别名搜索，query_product_details 也会返回别名信息
- 如果同一个名称可能匹配多个款号，必须先询问客户确认

## 五、图片和表格解析注意事项
1. **背面透字过滤**：如果图片中有纸张背面透过来的文字（颜色较浅、方向相反、镜像或模糊的印刷/手写痕迹），请完全忽略这些背面透字，只识别纸张正面清晰可见的内容
2. **手写内容**：手写内容模糊、涂改、无法辨认的数量，不要猜测，应询问客户确认
3. **一次消息多商品**：一条消息/图片/表格中可能包含多个商品的报货信息，要全部识别，每个款号+颜色单独一条记录
4. **表格数据**：Excel/表格中的数据要完整提取，注意表头和数据行的对应关系
5. 只提取货号、颜色、尺码、数量、备注信息，**不需要识别客户名、联系人、下单日期等无关信息**

## 六、订单意图判断（极其重要，必须区分两种情况）

### 情况A：替换旧单（replace）— 替换 ERP 中已下的历史订单
客户明确要**替换/作废之前已经下过的订单**（已经进入 ERP 系统的），关键词：
- "替换""换单""重新报""之前那个不要了""把昨天的单改一下""这个替换之前的""作废之前的""全部换成这个"
→ 调用 create_order_review 时设置 order_intent="replace"

### 情况B：更正刚发的报货（写错了/发错了）— 作废审核单后重新下
客户只是**更正刚才发的报货内容**（还没审核下单的），关键词：
- "刚才那个写错了""发错了""重新发一下""那张不要了换这个""上面那个不对"
→ 先调用 void_recent_review 作废刚才的审核单，再用 create_order_review 创建新的（order_intent="new"）

### 区分标准
- 情况A 指的是**已经在 ERP 中存在的历史订单**，客户要用新单完全取代旧单
- 情况B 指的是**刚才几分钟内发的报货消息写错了**，客户要更正
- 如果客户只是第二次发图片/消息，没有说"写错""发错""不要了"等，按**新下单**处理（情况都不是）

### 追加补充（append）
客户说"追加""再加""补几件""加一点" → order_intent="append"

如果没有明确的替换/追加/更正意图，默认为 new。

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
- **不需要回复的情况（直接忽略，不调用任何工具，不输出任何内容）：**
  - 日常闲聊、问候、表情包、与报货无关的对话
  - 客户回复了你之前询问的缺失信息（此时你应该继续处理订单，但不需要再次询问或重复确认）
  - 同一个报货任务的后续补充消息，如果前一条消息已经触发了处理流程，不要重复回复
  - 你已经对某条报货信息回复过确认，后续相同内容不要再次回复
  - **不确定是否为报单的消息**（参见步骤1 “不确定” 情况），在连续 3 条未确认之前不要主动询问

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
    review_uid = f"RV{datetime.now().strftime('%y%m%d')}{secrets.token_hex(2).upper()}"

    # 直接创建审核记录，parse_status=success（AI 已完成解析）
    parsed_order_json = json.dumps({"items": items}, ensure_ascii=False)
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
async def _download_attachment_from_cdn(
    db: Session,
    payload: dict[str, Any],
    instance_id: str,
    message_type: str,
) -> str:
    """尝试从企微 CDN 下载附件，返回 base64。失败时返回空字符串。"""
    try:
        from app.services.media_archive import _extract_cdn_params_from_payload, _resolve_runtime, _guess_extension
        from pathlib import Path

        cdn_params = _extract_cdn_params_from_payload(payload)
        if not cdn_params:
            logger.debug("CDN下载: 无CDN参数，跳过")
            return ""

        runtime = _resolve_runtime(db, instance_id)
        if not runtime.get("api_base_url") or not runtime.get("wxid"):
            logger.debug("CDN下载: 缺少运行时配置")
            return ""

        ext = _guess_extension("", message_type)
        download_dir = Path(__file__).resolve().parents[2] / "temp" / "ai_chat_attachments"
        download_dir.mkdir(parents=True, exist_ok=True)
        save_path = download_dir / f"chat_{secrets.token_hex(4)}{ext}"

        mode = cdn_params.pop("mode")
        api_route = f"cdn/{mode}"
        cdn_params["save_path"] = str(save_path)

        headers: dict[str, str] = {}
        if runtime.get("api_key"):
            headers["X-API-Key"] = runtime["api_key"]

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{runtime['api_base_url']}/api/{runtime['wxid']}/{api_route}",
                json=cdn_params,
                headers=headers,
            )
            resp.raise_for_status()
            resp_data = resp.json()

        if isinstance(resp_data, dict) and resp_data.get("code") not in (0, None):
            logger.warning("CDN下载失败: %s", resp_data.get("msg"))
            return ""

        # 检查文件是否存在
        if not save_path.is_file():
            data_body = resp_data.get("data") if isinstance(resp_data.get("data"), dict) else {}
            for key in ("save_path", "path", "file_path"):
                possible = str(data_body.get(key) or "").strip()
                if possible and Path(possible).is_file():
                    save_path = Path(possible)
                    break
        if not save_path.is_file():
            logger.warning("CDN下载: 文件不存在")
            return ""

        file_bytes = save_path.read_bytes()
        result_b64 = base64.b64encode(file_bytes).decode("ascii")
        logger.info("CDN下载成功: %d bytes", len(file_bytes))

        # 清理临时文件
        try:
            save_path.unlink(missing_ok=True)
        except Exception:
            pass

        return result_b64
    except Exception as exc:
        logger.warning("CDN下载异常: %s", exc)
        return ""


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
    """处理来自客户群的一条消息：追加到对话 → 调用 AI → 执行工具。

    返回: {"ok": True/False, "ai_responded": bool, ...}
    """
    ensure_chat_table(db)

    # ---- 0. 图片/文件缺失 base64 时尝试从 CDN 下载 ----
    is_media = message_type in ("image", "img", "picture", "file")
    if is_media and not attachment_base64 and payload:
        logger.info("图片/文件缺 base64，尝试 CDN 下载: room=%s type=%s", room_id, message_type)
        attachment_base64 = await _download_attachment_from_cdn(db, payload, instance_id, message_type)

    # ---- 1. 构建 user message content ----
    prefix = f"[{sender_name or sender_id}] "
    user_content: Any  # str 或 list (multimodal)

    if message_type in ("image", "img", "picture") and attachment_base64:
        # 图片: multimodal content
        user_content = [
            {"type": "text", "text": prefix + (content_text or "（发送了一张图片）")},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{attachment_base64}"}},
        ]
    elif message_type == "file" and file_name.lower().endswith((".xlsx", ".xls")) and attachment_base64:
        # Excel: 转 Markdown
        md_table = _excel_to_markdown(attachment_base64)
        if md_table:
            user_content = prefix + f"（发送了表格文件 {file_name}）\n\n{md_table}"
        else:
            user_content = prefix + f"（发送了文件 {file_name}，无法解析）"
    else:
        # 纯文字
        user_content = prefix + (content_text or "")

    # ---- 2. 保存 user message ----
    _save_message(db, room_id, "user", content=user_content, name=sender_name)

    # ---- 3. 加载对话历史 ----
    history = _load_history(db, room_id)

    # ---- 4. 组装 API messages (system + history) ----
    api_messages: list[dict[str, Any]] = [
        {"role": "system", "content": CUSTOMER_GROUP_SYSTEM_PROMPT},
    ]
    # 历史消息中如果有图片 base64，对于较早的消息去掉图片以节省 token
    for i, msg in enumerate(history):
        if isinstance(msg.get("content"), list) and i < len(history) - 5:
            # 5 条以前的图片消息，用文字替代
            text_parts = [p.get("text", "") for p in msg["content"] if p.get("type") == "text"]
            api_messages.append({"role": msg["role"], "content": " ".join(text_parts) + " [图片已省略]"})
        else:
            api_messages.append(msg)

    # ---- 5. 调用 AI (可能多轮 tool call) ----
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
        except Exception as exc:
            logger.error("AI API 调用失败: room=%s err=%s", room_id, exc)
            break

        choice = (ai_response.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        ai_content = message.get("content")
        tool_calls = message.get("tool_calls")

        # 保存 assistant 消息
        _save_message(
            db, room_id, "assistant",
            content=ai_content,
            tool_calls=tool_calls,
        )
        api_messages.append(message)

        if not tool_calls:
            # AI 没有调用工具 — 可能是普通回复或什么都不做
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

            # 执行
            tool_result = await _execute_tool(
                func_name, func_args,
                db=db, room_id=room_id, sender_id=sender_id,
                sender_name=sender_name, customer=customer,
                instance_id=instance_id,
            )

            # 保存 tool response
            _save_message(db, room_id, "tool", content=tool_result, name=func_name, tool_call_id=call_id)
            api_messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": tool_result,
            })
            ai_responded = True

    # ---- 6. 定期清理旧消息 ----
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

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    t0 = time.time()
    async with httpx.AsyncClient(timeout=CHAT_API_TIMEOUT) as client:
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
