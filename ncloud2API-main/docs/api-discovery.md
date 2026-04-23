# ncloud2 ERP API 抓包记录

> 通过 Playwright 自动化浏览器会话抓取，日期：2026-04-14
> ERP 基础地址：`http://nclouddl43.ywhzsoft.com:8154`

---

## 认证机制

所有接口均需先完成登录获取 session cookie，后续请求携带 cookie 即可。

### 登录流程

**Step 1：获取账套信息**
```
POST /Login/CheckAccountSet
Content-Type: multipart/form-data
Body: imgData=<二维码图片文件>

Response: {
  "Success": true,
  "Data": {
    "accountSetName": "韩酷服饰(NET)",
    "qrcode": "6CA644A6-D280-45C1-A924-919B571F6E41",
    "projectURL": null
  }
}
```

**Step 2：账号密码登录**
```
POST /Login/CheckLogin
Content-Type: application/x-www-form-urlencoded
Headers: X-Requested-With: XMLHttpRequest
Body: Account=测试&Password=123&qrcode=<Step1返回的qrcode>

Response: { "rs": "3" }   // rs=3 表示登录成功
```

> 说明：`qrcode` 也可直接从登录页 URL 的 `configCode` 参数获取，
> 无需每次上传图片（URL 格式：`/Login?configCode=6CA644A6-...`）。

---

## 公共请求头

所有 AJAX 接口必须携带：
```
X-Requested-With: XMLHttpRequest
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
```

---

## 销售订单模块

**对应页面路径**：`/SalesManagement/ClothingOrderDd/Index`
**表单页路径**：`/SalesManagement/ClothingOrderDd/Form?isAdd=<mode>&keyValue=<dh>`

mode 取值：`display`（查看）、`modify`（修改）、`add`（新增）

---

### 1. 销售订单列表

```
POST /SalesManagement/ClothingOrderDd/GridPageListJson
Body: dates=2026-04-01&datee=2026-04-14&state=["0","1"]&page=1&rows=1000

Response: {
  "total": 251,
  "rows": [
    {
      "dh": "20260414-004",      // 单号
      "zhdate": "2026-04-14 10:32:20",  // 订单日期
      "state": 1,                // 0=编辑, 1=审核
      "printnum": 0,             // 印次
      "khid": "0404",            // 客户编号
      "khname": "蔡竹林",        // 客户名称（列表接口直接返回）
      "khtel": "13612351888",    // 客户电话
      "khaddr": "...",           // 客户地址
      "ywy": "",                 // 业务员
      "huohao_mx": "95862",      // 货号汇总
      "je_sum": 0,               // 合计金额
      "sl_sum": 100,             // 合计数量
      "zhuser": "客服",          // 制单人
      // ... 更多字段
    }
  ]
}
```

### 2. 销售订单详情

```
POST /SalesManagement/ClothingOrderDd/GetEntity
Body: dh=20260414-004

Response: {
  "main": {
    "dh": "20260414-004",
    "zhdate": "2026-04-14 10:32:20",
    "zhuser": "客服",          // 制单人
    "khid": "0404",
    "khaddr": "成都市金牛区...",
    "khtel": "13612351888",
    "shaddr": "",              // 托运地址
    "shtel": "",               // 托运电话
    "fkfs": null,              // 付款方式
    "tyfs": "",                // 托运方式
    "fkje": null,              // 收款金额
    "yhje": 0,                 // 优惠金额
    "remark": "",
    "state": 1,                // 0=编辑, 1=审核
    "printnum": 0,
    "fhdate": null,            // 交货日期
    "ywy": "",                 // 业务员
    "ddh": "",                 // 订单号
    "je_sum": 0,               // 合计金额
    "sl_sum": 100,             // 合计数量
    "bizhong": "",             // 币种
    "state_sh": 0,             // 财审状态
    "sfplan": "否",            // 是否计划
    "price_print": 1,          // 单价打印
    "jh_date": null,           // 计划日期
    "fkguid": "e1e6d33c-...",  // 内部GUID
    // ... 更多字段
  },
  "detail": [
    {
      "id": "A8DD33FC-...",    // 行UUID
      "dh": "20260414-004",
      "spbh": "0034",          // 品牌编号
      "huohao": "00152",       // 货号
      "spname": "",            // 品名
      "chima": null,           // 尺码组
      "zk": 100,               // 折扣
      "chimadetail": [
        {
          "id": "67D13E47-...",
          "dh": "20260414-004",
          "detailId": "A8DD33FC-...",
          "field": "XL",       // 尺码名
          "value": 15,         // 数量
          "ddWfhsl": 15,       // 订单未发货数量
          "ddfhsl": 0,         // 订单已发货数量
          "ddthsl": 0,         // 退货数量
          "kfsl": null,        // 可发数量
          "DeleteMark": 0
        }
        // ... 其他尺码
      ]
    }
  ]
}
```

### 3. 添加/修改销售单

```
POST /SalesManagement/ClothingOrderDd/SubmitForm
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

Body:
  isAdd=true                     // true=新增, false=修改
  &mainData=<JSON string>        // 主表数据
  &detailData=<JSON string>      // 明细行数组
  &fkData=[]                     // 付款数据（数组，可空）
  &htData=<JSON string>          // 合同数据（对象）

Response (成功):
  { "Success": true, "Type": 1, "Data": "20260414-014", "Message": "保存成功。" }
  // Data = 生成的单号 dh
```

**mainData 字段**：

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| dh | — | string | 修改时传入单号，新增时传空 |
| zhdate | ✅ | string | 订单日期 `YYYY-MM-DD HH:mm:ss` |
| zhuser | — | string | 制单人 |
| khid | ✅ | string | 客户编号（如 "0218"）|
| khaddr | — | string | 客户地址 |
| khtel | — | string | 客户电话 |
| shaddr | — | string | 托运地址 |
| shtel | — | string | 托运电话 |
| tyfs | — | string | 托运方式 |
| fkje | — | number/null | 收款金额 |
| yhje | — | number | 优惠金额 |
| remark | — | string | 备注 |
| state | — | int | 状态 0=编辑（新增时传0）|
| ywy | — | string | 业务员 |
| ddh | — | string | 订单号（客户自定义，非系统单号）|
| bizhong | — | string | 币种 |
| sfplan | — | string | 是否计划 "是"/"否" |
| price_print | — | int | 单价打印 1=是 |
| khtype | — | string | 客户类型 |
| main_spbh | — | string | 品牌 |

**detailData 字段**（数组中每项）：

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| spbh | — | string | 品牌编号 |
| huohao | ✅ | string | 货号 |
| spname | — | string | 品名 |
| chima | — | null | 尺码组 |
| zk | — | int | 折扣（默认100）|
| color | — | string | 颜色 |
| xs | ✅ | int | 合计数量 |
| dw | — | string | 单位 |
| price | — | number | 单价 |
| remark | — | string | 备注 |
| sort | — | int | 排序号 |
| bzfs | — | string | 包装方式 |
| khhh | — | string | 客户货号 |
| khgrade | — | string | 销售等级 |
| chimadetail | ✅ | array | 尺码明细数组 |

**chimadetail 项**：`{ "field": "S", "value": 1, "DeleteMark": 0 }`

**htData**（合同数据对象）：
```json
{ "dh": "", "guid": "", "zsl": null, "mxsl": null, "xiangshu": null, "DeleteMark": 0 }
```

### 4. 审核/作废销售单

**审核**：
```
POST /SalesManagement/ClothingOrderDd/DdshenHe
Body: dh=20260414-014

Response: { "Success": true, "Type": 1, "Data": "1", "Message": "作废成功。" }
// 注意：Message 文本不准确，实际执行的是审核操作（state: 0→1）
```

**反审**（销售订单也有反审，在表单页触发）：
```
POST /SalesManagement/ClothingOrderDd/UnExamine
Body: dh=20260414-014&type=销售订单

Response: { "Success": true, "Type": 1, "Data": "1", "Message": "更新成功。" }
// state: 1→0
```

**作废**：
```
POST /SalesManagement/ClothingOrderDd/Delete
Body: dh=20260414-014

Response: { "Success": true, "Type": 1, "Data": "1", "Message": "作废成功。" }
// state: →2
```

状态机：`0(编辑) ↔ 1(审核) → 2(作废)`

### 5. 修改销售单

与添加使用同一接口 `SubmitForm`，区别：
- `isAdd=false`
- `mainData` 中 `dh` 传入已有单号
- 修改前单据必须为编辑状态（state=0），已审核的需先反审

---

## 销售发货单模块

**对应页面路径**：`/SalesManagement/ClothingOrder/Index`
**表单页路径**：`/SalesManagement/ClothingOrder/Form?isAdd=<mode>&keyValue=<dh>`

---

### 6. 销售发货单列表

```
POST /SalesManagement/ClothingOrder/GridPageListJson
Body: dates=2026-04-01&datee=2026-04-14&state=["0","1"]&page=1&rows=1000

Response: {
  "total": 702,
  "rows": [
    {
      "dh": "20260414-002",      // 发货单号
      "zhdate": "2026-04-14 10:38:16",  // 发货日期
      "zhuser": "管理员",        // 制单人
      "khid": "0526",
      "khaddr": "浙江省杭州市...",
      "shaddr": "",              // 托运地址
      "shtel": "",
      "shuser": "",              // 送货人
      "state": 1,                // 0=编辑, 1=审核
      "link_man": "熊贻聪",      // 联系人
      "tel1": "18870260862",     // 联系电话
      "yunhao": "",              // 运单号
      "yunfei": null,            // 运费
      "ck": "0001",              // 发货仓库
      "je_sum": 165,             // 合计金额
      "fhzsl": 5,                // 发货总数量
      "sffk": 0,                 // 是否付款
      "sf_monthly": 0,           // 是否月结
      "fkguid": "fd262b3e-...",
      // ... 更多字段
    }
  ]
}
```

### 7. 销售发货单详情

```
POST /SalesManagement/ClothingOrder/GetEntity
Body: dh=20260414-002

Response: {
  "main": {
    // 同列表行字段，更完整
    "dh": "20260414-002",
    "zhdate": "2026-04-14 10:38:16",
    "khid": "0526",
    "khaddr": "...",
    "ck": "0001",              // 发货仓库（必填）
    "yunhao": "",              // 运单号
    "yunfei": null,            // 运费
    "link_man": "熊贻聪",
    "tel1": "18870260862",
    "state": 1,
    "je_sum": 165,
    "fhzsl": 5,
    "shr": "管理员",           // 审核人
    "shsj": "2026-04-14 10:38:49",  // 审核时间
    // ...
  },
  "detail": [
    {
      "id": "D4C3AA8A-...",
      "dh": "20260414-002",
      "ddid": null,            // 关联订单行ID
      "spbh": "",              // 品牌
      "huohao": "00147",       // 货号
      // chimadetail 同销售订单结构
    }
  ]
}
```

### 8. 添加/修改销售发货单

```
POST /SalesManagement/ClothingOrder/SubmitForm
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

Body:
  isAdd=true                     // true=新增, false=修改
  &mainData=<JSON string>        // 主表数据
  &detailData=<JSON string>      // 明细行数组
  &fkData=[]                     // 付款数据（数组，可空）
  &resend=0                      // 微信推送标记（默认0）
  &khqk=                         // 客户欠款信息（可空）

Response (成功):
  { "Success": true, "Type": 1, "Data": "20260414-035", "Message": "保存成功。" }
```

**mainData 字段**（与销售订单差异标注 ⚡）：

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| dh | — | string | 修改时传入单号，新增时传空 |
| zhdate | ✅ | string | 发货日期 `YYYY-MM-DD HH:mm:ss` |
| zhuser | — | string | 制单人 |
| khid | ✅ | string | 客户编号 |
| khaddr | — | string | 客户地址 |
| shaddr | — | string | 托运地址 |
| shtel | — | string | 托运电话 |
| shuser | — | string | ⚡ 送货人（订单无此字段）|
| tyfs | — | string | 托运方式 |
| yunhao | — | string | ⚡ 运单号 |
| yunfei | — | number/null | ⚡ 运费 |
| fkje | — | number/null | 收款金额 |
| yhje | — | number | 优惠金额 |
| remark | — | string | 备注 |
| state | — | int | 状态 0=编辑 |
| ywy | — | string | 业务员 |
| ck | ✅ | string | ⚡ 发货仓库编号（如 "0001"）|
| bizhong | — | string | 币种 |
| price_print | — | int | 单价打印 |
| tel1 | — | string | 联系电话 |
| link_man | — | string | 联系人 |
| khtype | — | string | 客户类型 |
| ddh | — | string | 订单号 |

**detailData 字段**（与销售订单差异标注 ⚡）：

| 字段 | 必填 | 类型 | 说明 |
|------|------|------|------|
| spbh | — | string | 品牌编号 |
| huohao | ✅ | string | 货号 |
| spname | — | string | 品名 |
| zk | — | int | 折扣（默认100）|
| color | ✅ | string | ⚡ 颜色（发货单必填）|
| xs | ✅ | int | 合计数量 |
| dw | — | string | 单位 |
| price | — | number | 单价 |
| remark | — | string | 备注 |
| sort | — | int | 排序号 |
| bzfs | — | string | 包装方式 |
| khhh | — | string | 客户货号 |
| ddid | — | string/null | ⚡ 关联销售订单行ID |
| chimadetail | ✅ | array | 尺码明细数组 |

> 注意：发货单没有 `htData` 参数，额外有 `resend` 和 `khqk` 参数。

### 9. 审核/反审/作废销售发货单

**审核**：
```
POST /SalesManagement/ClothingOrder/shenHe
Body: dh=20260414-035

Response: { "Success": true, "Type": 1, "Data": "1", "Message": "作废成功。" }
// 注意：Message 文本不准确，实际执行审核（state: 0→1）
```

**反审**：
```
POST /SalesManagement/ClothingOrder/UnExamine
Body: dh=20260414-035

Response: { "Success": true, "Type": 1, "Data": "1", "Message": "更新成功。" }
// state: 1→0
```

**作废**：
```
POST /SalesManagement/ClothingOrder/Delete
Body: dh=20260414-035

Response: { "Success": true, "Type": 1, "Data": "1", "Message": "删除成功。" }
// state: →2
```

状态机：`0(编辑) ↔ 1(审核) → 2(作废)`

### 10. 修改发货单

与添加使用同一接口 `SubmitForm`，区别：
- `isAdd=false`
- `mainData` 中 `dh` 传入已有单号
- 修改前单据必须为编辑状态（state=0），已审核的需先反审

---

## 销售对账单模块

**对应页面路径**：`/SalesManagement/DuizhangOder/CustomerStatement`

### 11. 客户列表（对账单页左侧）

```
POST /PublicApp/PublicQuery/GetBaseInfoList
Body: param=customs

Response: {
  "customs": [
    { "bh": "0001", "name": "钟江锋", "name_pk": "zjf", ... },   // bh=编号, name=名称
    { "bh": "0002", "name": "朱满云", "name_pk": "zmy", ... },
    // ... 共527条
  ]
}
```

### 12. 销售对账单

```
POST /SalesManagement/DuizhangOder/GetReportData
Content-Type: application/x-www-form-urlencoded
Body:
  sortRules=zhdate+asc%2Czdtype+asc
  &reportFilterRules=[
    {"field":"zhdate","type":"date","filterOp":"sql","op":"greaterorequal","value":"2026-04-01"},
    {"field":"zhdate","type":"date","filterOp":"sql","op":"lessorequal","value":"2026-04-14"},
    {"field":"isshowqc","type":"","filterOp":"other","op":"equal","value":"1"},
    {"field":"khid","filterOp":"sql","op":"equal","value":"0001"},
    {"field":"sfjz","filterOp":"sql","op":"notequal","value":"1"}
  ]
  &total=true
  &subTotalState=true
  &reportColumnParams=[...列配置 JSON，见下方...]
  &page=1&rows=750

Response 字段（rows数组）:
  zhdate    日期
  zdtype    账单类型（发货/收款/退货/运费）
  xs        总数量
  je        金额
  yfje      应收金额
  fkje      已收金额
  qje       应收余额
  dh        单号
```

**reportColumnParams 固定列配置**（页面初始化时从服务端获取，实际为静态数据，可硬编码）：

| 字段名 | 列名 | 显示 |
|--------|------|------|
| zhdate | 日期 | 是 |
| zdtype | 账单类型 | 是 |
| xs | 总数量 | 是 |
| je | 金额 | 是 |
| yfje | 应收金额 | 是 |
| fkje | 已收金额 | 是 |
| qje | 应收余额 | 是 |
| dh | 单号 | 否（隐藏）|
| huohao | 货号 | 否 |
| color | 颜色 | 否 |
| price | 销售单价 | 否 |
| yunhao | 运号 | 否 |
| remark | 备注 | 否 |

> 完整 `reportColumnParams` JSON 已通过 Playwright 网络抓包获取，
> 可在 `app/services/reconciliation.py` 中硬编码该值。

---

## 其他有用接口

### 基础数据查询（通用）

```
POST /PublicApp/PublicQuery/GetBaseInfoList
Body: param=<类型>

支持的 param 值:
  customs         客户列表（返回 bh=编号, mc=名称）
  employee        员工列表
  chima           尺码配置
  cpbbreed        品牌列表
  pinpai          品牌
  khkhgrade       客户等级
  huohaoguige     货号规格
  bzfs            包装方式
  huohaocolor     货号颜色
  bizhong         币种
  khtype          客户类型
  tyfs            托运方式
```

### 权限按钮查询

```
POST /PublicApp/PublicQuery/AuthorizedButtons
Body: permissionPage=/SalesManagement/ClothingOrderDd
```

### 附件查询

```
POST /Upload/GetSingle
Body: module=订单合同&key=<单号>&sort=0
```

---

## 写接口汇总

> 已通过 Playwright 抓包确认（2026-04-14），详见上方各模块章节。

| 操作 | 端点 URL | 参数 |
|------|----------|------|
| 添加销售单 | `POST .../ClothingOrderDd/SubmitForm` | isAdd=true, mainData, detailData, fkData, htData |
| 修改销售单 | `POST .../ClothingOrderDd/SubmitForm` | isAdd=false, mainData(含dh), detailData, fkData, htData |
| 审核销售单 | `POST .../ClothingOrderDd/DdshenHe` | dh |
| 反审销售单 | `POST .../ClothingOrderDd/UnExamine` | dh, type=销售订单 |
| 作废销售单 | `POST .../ClothingOrderDd/Delete` | dh |
| 添加发货单 | `POST .../ClothingOrder/SubmitForm` | isAdd=true, mainData, detailData, fkData, resend, khqk |
| 修改发货单 | `POST .../ClothingOrder/SubmitForm` | isAdd=false, mainData(含dh), detailData, fkData, resend, khqk |
| 审核发货单 | `POST .../ClothingOrder/shenHe` | dh |
| 反审发货单 | `POST .../ClothingOrder/UnExamine` | dh |
| 作废发货单 | `POST .../ClothingOrder/Delete` | dh |

---

## 未发货统计报表模块

**对应页面路径**：`/SalesManagement/ClothingOrderDd/WfhReport`

---

### 13. 未发货统计报表查询

```
POST /SalesManagement/ClothingOrderDd/GetWfhReportData
Body:
  sortRules=zhdate+asc%2Cdh+asc%2Chuohao+asc
  &reportFilterRules=[
    {"field":"sfwg","type":"","filterOp":"other","op":"equal","value":"0"},
    {"field":"xscdd","type":"","filterOp":"other","op":"equal","value":"0"},
    {"field":"zhdate","type":"date","filterOp":"sql","op":"greaterorequal","value":"2026-04-14"},
    {"field":"zhdate","type":"date","filterOp":"sql","op":"lessorequal","value":"2026-04-15"}
  ]
  &total=true
  &subTotalState=true
  &subTotalGroupRules=zhdate,dh
  &reportColumnParams=[]
  &page=1&rows=750

Response: {
  "total": 75,
  "rows": [
    {
      "id": "4D1D7D4C-...",      // 行唯一标识
      "dh": "20260414-001",      // 订单号
      "zhdate": "2026-04-14",    // 订单日期
      "khid": "0501",            // 客户编号
      "spbh": "0033",            // 品牌
      "huohao": "00143",         // 货号
      "color": "云舞白",          // 颜色
      "dw": "条",                // 单位
      "zsl": 5,                  // 订单数量
      "fhsl": 0,                 // 发货数量
      "thsl": 0,                 // 退货数量
      "wfhsl": 5,                // 未发货数量
      "wfhje": 0,                // 未发货金额
      "kcsl": 272,               // 库存数量
      "price": 0,                // 销售单价
      "cbprice": 0,              // 成本价
      "dp_price": 0,             // 吊牌价
      "zhuser": "客服",          // 制单人
      "chimadetail": [...],      // 订单尺码明细
      "wfhchimadetail": [...],   // 未发货尺码明细（含 fhvalue/thvalue/wfhvalue）
      "kcchimadetail": [...]     // 库存尺码明细
    }
  ]
}
```

> `reportColumnParams` 可传空数组 `[]`，后端仍返回完整字段。
> `crossColumns` 可不传，尺码数据以嵌套数组返回。

---

### 14. 取消发货 / 还原订单

```
POST /SalesManagement/ClothingOrderDd/CancelFh
Body: data=[{"id":"<行ID>","sfwg":1}]

// sfwg=1 → 取消发货（标记手动完工）
// sfwg=0 → 还原订单（撤销手动完工）
// 支持批量，data 数组可传多个

Response: { "Success": true, "Type": 1, "Data": "1", "Message": "保存成功" }
```

> 取消发货和还原订单是同一个端点，通过 `sfwg` 参数区分。
> `id` 来自报表查询结果中每行的 `id` 字段。

---

## 成品库存模块

**对应页面路径**：`/CpHandwork/HandworkCpInventory/InventoryZReport`

---

### 15. 成品库存总报表查询

```
POST /CpHandwork/HandWorkCpInventory/GetZReportDataCosswise
Body:
  sortRules=ck+asc%2Chuohao+asc%2Ccolor+asc
  &reportFilterRules=[
    {"field":"zeroInventory","type":"","filterOp":"other","op":"equal","value":"0"},
    {"field":"fuInventory","type":"","filterOp":"other","op":"equal","value":"0"}
  ]
  &total=true
  &subTotalState=true
  &subTotalGroupRules=
  &reportColumnParams=[]
  &page=1&rows=750

Response: {
  "total": 498,
  "rows": [
    {
      "ck": "0001",              // 仓库编号
      "huohaotypename": "0007",  // 货号类别
      "huohao": "00001",         // 货号
      "description": "",         // 品名
      "caizhi": "",              // 材质
      "FileUrl": "",             // 图片URL
      "color": "薄荷曼波绿",      // 颜色
      "dw": "条",                // 单位
      "sl": 437,                 // 库存数量
      "xsprice": 0,              // 销售价
      "cbprice": 0,              // 成本价
      "je": 0,                   // 金额
      "ztsl": 0,                 // 生产在途数
      "chimadetail": [           // 各尺码库存
        {"field": "M", "value": 26},
        {"field": "L", "value": 150},
        ...
      ]
    }
  ]
}
```

> 与未发货报表一样，`reportColumnParams` 可传空数组。
> 过滤条件：`zeroInventory=0` 不显示零库存，`fuInventory=0` 不显示负库存。
