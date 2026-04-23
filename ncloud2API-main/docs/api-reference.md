# ncloud2API 接口文档

> 基础地址：`http://127.0.0.1:8000`
>
> 启动后也可以访问 `http://127.0.0.1:8000/docs` 查看自动生成的交互式文档。

---

## 通用说明

### 请求格式

- GET 请求的参数放在 URL 查询字符串中（`?key=value`）
- POST / PUT 请求的参数放在请求体中，格式为 JSON，需要设置 `Content-Type: application/json`

### 返回格式

所有接口返回 JSON。成功时直接返回业务数据，失败时返回统一的错误结构：

```json
{
  "error": "错误代码",
  "message": "错误描述（中文）"
}
```

### 常见错误码

| HTTP 状态码 | error | 什么时候出现 |
|-------------|-------|-------------|
| 404 | `ORDER_NOT_FOUND` | 找不到这个订单号 |
| 404 | `SHIPMENT_NOT_FOUND` | 找不到这个发货单号 |
| 404 | `CUSTOMER_NOT_FOUND` | 客户名称没匹配到 |
| 409 | `ORDER_NOT_EDITABLE` | 订单已审核，不能修改 |
| 409 | `SHIPMENT_NOT_EDITABLE` | 发货单已审核，不能修改 |
| 422 | `AMBIGUOUS_CUSTOMER` | 客户名匹配到多个人 |
| 422 | `MISSING_CUSTOMER` | 没有提供客户名或客户 ID |
| 422 | — | 参数格式不对（FastAPI 自动校验） |
| 502 | `ERP_UPSTREAM_ERROR` | ERP 系统访问不了或返回异常 |
| 502 | `ERP_AUTH_ERROR` | ERP 登录失败 |

### 使用前提

调用业务接口前，需要先调一次 **登录接口**（`POST /api/login`），登录后同一个服务进程内的所有请求都会自动复用会话，不需要额外传 token。如果会话过期，系统会自动重新登录。

---

## 1. 登录

### `POST /api/login`

登录 ERP 系统，建立会话。服务启动后调用一次即可。

**参数**：无

**返回示例**：

```json
{
  "account_set_name": "韩酷服饰(NET)",
  "qrcode": "6CA644A6-D280-45C1-A924-919B571F6E41",
  "project_url": "http://nclouddl43.ywhzsoft.com:8154/Login",
  "login_rs": "3"
}
```

| 字段 | 说明 |
|------|------|
| `account_set_name` | 账套名称 |
| `login_rs` | 登录结果，`"3"` 表示成功 |

---

## 2. 获取账套信息

### `GET /api/account-set`

获取当前连接的 ERP 账套信息。

**参数**：无

**返回示例**：

```json
{
  "account_set_name": "韩酷服饰(NET)",
  "qrcode": "6CA644A6-...",
  "project_url": "http://nclouddl43.ywhzsoft.com:8154/Login"
}
```

---

## 3. 货号列表

### `GET /api/products`

获取 ERP 中的货号（商品）列表。

**参数**：

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `page` | 否 | 数字 | 页码，默认 1 |
| `rows` | 否 | 数字 | 每页条数，默认 20，最大 500 |

**返回示例**：

```json
{
  "total": 707,
  "rows": [
    {
      "bh": "00001",
      "bbreed": "82708",
      "dw": "条",
      "xsprice": 0.0,
      "zxsrequire1": "薄荷曼波绿,高级灰,...",
      "zxsrequire2": "M,L,XL,2XL,3XL",
      ...
    }
  ]
}
```

> `rows` 中的字段是 ERP 原始字段，常用的有：
> - `bh` — 货号编码
> - `bbreed` — 品牌编码
> - `dw` — 单位
> - `zxsrequire1` — 可选颜色（逗号分隔）
> - `zxsrequire2` — 可选尺码（逗号分隔）

---

## 4. 销售订单

### 4.1 获取订单列表

#### `GET /api/sales-orders`

按日期范围查询销售订单。

**参数**：

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `dates` | 是 | 字符串 | 起始日期，如 `2026-04-01` |
| `datee` | 是 | 字符串 | 结束日期，如 `2026-04-14` |
| `state` | 否 | 字符串数组 | 状态过滤，`0`=编辑中 `1`=已审核，默认两个都查 |
| `page` | 否 | 数字 | 页码，默认 1 |
| `rows` | 否 | 数字 | 每页条数，默认 20，最大 1000 |

**请求示例**：

```
GET /api/sales-orders?dates=2026-04-01&datee=2026-04-14&rows=5
```

**返回示例**：

```json
{
  "total": 247,
  "rows": [
    {
      "state": 1,
      "print_count": 0,
      "order_no": "20260413-020",
      "order_date": "2026-04-13 19:05:55",
      "creator": "客服",
      "customer_id": "0186",
      "customer_name": "张三",
      "customer_tel": "13800138000",
      "customer_addr": "清河",
      "product_no": "95862",
      "total_amount": 0.0,
      "total_qty": 2670.0,
      "salesperson": ""
    }
  ]
}
```

**rows 字段说明**：

| 字段 | 说明 |
|------|------|
| `state` | 0=编辑中，1=已审核 |
| `print_count` | 打印次数 |
| `order_no` | 订单号 |
| `order_date` | 下单日期 |
| `creator` | 制单人 |
| `customer_id` | 客户编号 |
| `customer_name` | 客户名称 |
| `customer_tel` | 客户电话 |
| `customer_addr` | 客户地址 |
| `product_no` | 货号汇总 |
| `total_amount` | 总金额 |
| `total_qty` | 总数量 |
| `salesperson` | 业务员 |

> **BREAKING**：此接口原先返回 ERP 原始字段名（如 `dh`、`khname`、`je_sum`），现已改为规范化字段名。

---

### 4.2 获取订单详情

#### `GET /api/sales-orders/{dh}`

查询一个订单的完整信息，包括主表和明细行（含各尺码数量）。

**参数**：

| 参数 | 位置 | 说明 |
|------|------|------|
| `dh` | URL 路径 | 订单号，如 `20260413-020` |

**请求示例**：

```
GET /api/sales-orders/20260413-020
```

**返回示例**：

```json
{
  "main": {
    "order_no": "20260413-020",
    "order_date": "2026-04-13 19:05:55",
    "customer_id": "0186",
    "customer_name": null,
    "state": 1,
    "creator": "客服",
    "customer_tel": "13800138000",
    "customer_addr": "清河",
    "salesperson": "",
    "shipping_method": "",
    "shipping_tel": "",
    "shipping_addr": "",
    "order_ref": "",
    "delivery_date": "",
    "plan": "否",
    "currency": "",
    "price_print": 1,
    "payment_amount": null,
    "brand": "0034",
    "customer_type": "",
    "contact_person": "",
    "total_qty": 2670.0,
    "total_amount": 0.0,
    "discount_amount": 0,
    "remark": ""
  },
  "detail": [
    {
      "brand": "0033",
      "product_no": "00143",
      "sizes": [
        { "size": "L", "qty": 150 },
        { "size": "XL", "qty": 150 }
      ],
      "grade": "",
      "customer_product_no": "",
      "product_name": "",
      "packaging": "",
      "color": "",
      "price": 0,
      "discount": 100,
      "unit": "",
      "remark": ""
    }
  ]
}
```

**main 字段说明**：

| 字段 | 说明 |
|------|------|
| `order_no` | 订单号 |
| `order_date` | 下单日期 |
| `customer_id` | 客户编号 |
| `customer_name` | 客户名称（可能为 null） |
| `state` | 0=编辑中，1=已审核 |
| `creator` | 制单人 |
| `customer_tel` | 客户电话 |
| `customer_addr` | 客户地址 |
| `salesperson` | 业务员 |
| `shipping_method` | 托运方式 |
| `shipping_tel` | 托运电话 |
| `shipping_addr` | 托运地址 |
| `order_ref` | 客户订单号 |
| `delivery_date` | 交货日期 |
| `plan` | 是否下计划 |
| `currency` | 币种 |
| `price_print` | 单价打印（1=是，0=否） |
| `payment_amount` | 收款金额 |
| `brand` | 主品牌编码 |
| `customer_type` | 客户类型 |
| `contact_person` | 联系人 |
| `total_qty` | 总数量 |
| `total_amount` | 总金额 |
| `discount_amount` | 优惠金额 |
| `remark` | 备注 |

**detail 字段说明**：

| 字段 | 说明 |
|------|------|
| `brand` | 品牌编码 |
| `product_no` | 货号 |
| `sizes` | 各尺码数量 |
| `grade` | 销售等级 |
| `customer_product_no` | 客户货号 |
| `product_name` | 品名 |
| `packaging` | 包装方式 |
| `color` | 颜色 |
| `price` | 单价 |
| `discount` | 折扣 |
| `unit` | 单位 |
| `remark` | 行备注 |

**错误**：如果订单号不存在，返回 404：

```json
{ "error": "ORDER_NOT_FOUND", "message": "订单 20260413-999 不存在" }
```

---

### 4.3 创建订单

#### `POST /api/sales-orders`

创建一个新的销售订单。创建后状态为编辑中（`state=0`）。

**请求体**：

```json
{
  "customer_id": "0218",
  "order_date": "2026-04-14 00:00:00",
  "customer_addr": "成都市金牛区",
  "customer_tel": "13800138000",
  "remark": "测试订单",
  "salesperson": "",
  "order_ref": "",
  "detail": [
    {
      "product_no": "00001",
      "brand": "0034",
      "color": "",
      "sizes": [
        { "size": "L", "qty": 10 },
        { "size": "XL", "qty": 20 }
      ]
    }
  ]
}
```

**字段说明**：

| 字段 | 必填 | 说明 |
|------|------|------|
| `customer_id` | 是 | 客户编号（在 ERP 中的编号，如 `0218`） |
| `order_date` | 是 | 订单日期，格式 `YYYY-MM-DD HH:mm:ss` |
| `detail` | 是 | 明细行数组，至少 1 行 |
| `customer_addr` | 否 | 客户地址 |
| `customer_tel` | 否 | 客户电话 |
| `shipping_addr` | 否 | 收货地址 |
| `shipping_tel` | 否 | 收货电话 |
| `shipping_method` | 否 | 运输方式 |
| `salesperson` | 否 | 业务员 |
| `order_ref` | 否 | 客户自己的订单号 |
| `currency` | 否 | 币种 |
| `brand` | 否 | 主品牌编码 |
| `customer_type` | 否 | 客户类型 |
| `delivery_date` | 否 | 交货日期，格式 `YYYY-MM-DD` |
| `contact_person` | 否 | 联系人 |
| `plan` | 否 | 是否下计划，`"是"` 或 `"否"`，默认 `"否"` |
| `price_print` | 否 | 是否打印单价，`1`=是 `0`=否，默认 1 |
| `payment_amount` | 否 | 收款金额（配合收款功能使用，一般不传） |
| `remark` | 否 | 备注 |

**明细行字段**：

| 字段 | 必填 | 说明 |
|------|------|------|
| `product_no` | 是 | 货号 |
| `sizes` | 是 | 各尺码数量数组，如 `[{"size": "XL", "qty": 10}]` |
| `brand` | 否 | 品牌编码 |
| `color` | 否 | 颜色 |
| `unit` | 否 | 单位 |
| `price` | 否 | 单价，默认 0 |
| `discount` | 否 | 折扣百分比，默认 100（即不打折） |
| `packaging` | 否 | 包装方式 |
| `customer_product_no` | 否 | 客户货号 |
| `grade` | 否 | 销售等级 |
| `product_spec` | 否 | 货号规格 |
| `semi_product_no` | 否 | 半成品货号 |
| `linked_order_ref` | 否 | 关联订单号 |
| `remark` | 否 | 行备注 |

**返回示例**（HTTP 201）：

```json
{
  "dh": "20260414-018",
  "message": "保存成功。",
  "state": 0
}
```

| 字段 | 说明 |
|------|------|
| `dh` | 系统生成的订单号 |
| `message` | ERP 返回的提示信息 |
| `state` | 当前状态，0=编辑中 |

---

### 4.4 修改订单

#### `PUT /api/sales-orders/{dh}`

修改一个处于编辑中（`state=0`）的订单。只传需要改的字段，没传的保持原值。

**注意**：已审核的订单不能直接修改，需要先反审。

**请求示例**：

```
PUT /api/sales-orders/20260414-018
```

```json
{
  "remark": "修改后的备注",
  "customer_addr": "新地址"
}
```

如果要改明细行，需要传完整的 `detail` 数组（会整体替换）：

```json
{
  "detail": [
    {
      "product_no": "00001",
      "brand": "0034",
      "sizes": [
        { "size": "L", "qty": 5 },
        { "size": "XL", "qty": 10 }
      ]
    }
  ]
}
```

**返回示例**：

```json
{
  "dh": "20260414-018",
  "message": "保存成功。",
  "state": 0
}
```

**错误**：

- 订单不存在 → 404
- 订单已审核 → 409 `ORDER_NOT_EDITABLE`

---

### 4.5 审核 / 反审 / 作废订单

#### `POST /api/sales-orders/{dh}/audit`

对订单执行审核操作。

**请求体**：

```json
{
  "action": "audit"
}
```

| action 值 | 说明 | 操作前状态 → 操作后状态 |
|-----------|------|----------------------|
| `audit` | 审核 | 编辑中(0) → 已审核(1) |
| `unaudit` | 反审（撤销审核） | 已审核(1) → 编辑中(0) |
| `void` | 作废（删除） | 编辑中(0) → 已作废(2) |

**返回示例**：

```json
{
  "dh": "20260414-018",
  "message": "作废成功。",
  "state": 1
}
```

---

## 5. 销售发货单

### 5.1 获取发货单列表

#### `GET /api/sales-shipments`

按日期范围查询发货单列表。

**参数**：

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `dates` | 是 | 字符串 | 起始日期 |
| `datee` | 是 | 字符串 | 结束日期 |
| `state` | 否 | 字符串数组 | 状态过滤，默认 `["0","1"]` |
| `page` | 否 | 数字 | 页码，默认 1 |
| `rows` | 否 | 数字 | 每页条数，默认 20，最大 1000 |

**请求示例**：

```
GET /api/sales-shipments?dates=2026-04-01&datee=2026-04-14&rows=5
```

**返回示例**：

```json
{
  "total": 700,
  "rows": [
    {
      "order_no": "20260413-059",
      "order_date": "2026-04-13 19:54:30",
      "customer_id": "0199",
      "customer_addr": "",
      "state": 1,
      "total_qty": 55.0,
      "total_amount": 1550.0,
      "tracking_no": "",
      "customer_name": "王五",
      "print_count": 0,
      "salesperson": "",
      "shipping_addr": "",
      "shipping_method": "",
      "freight": null
    }
  ]
}
```

**rows 字段说明**：

| 字段 | 说明 |
|------|------|
| `order_no` | 发货单号 |
| `order_date` | 发货日期 |
| `customer_id` | 客户编号 |
| `customer_addr` | 客户地址 |
| `state` | 0=编辑中，1=已审核 |
| `total_qty` | 总发货数量 |
| `total_amount` | 总金额 |
| `tracking_no` | 物流单号 |
| `customer_name` | 客户名称 |
| `print_count` | 打印次数 |
| `salesperson` | 业务员 |
| `shipping_addr` | 托运地址 |
| `shipping_method` | 托运方式 |
| `freight` | 运费 |

---

### 5.2 获取发货单详情

#### `GET /api/sales-shipments/{dh}`

查询发货单的完整信息。

**请求示例**：

```
GET /api/sales-shipments/20260413-059
```

**返回示例**：

```json
{
  "main": {
    "order_no": "20260413-059",
    "order_date": "2026-04-13 19:54:30",
    "customer_id": "0199",
    "customer_addr": "",
    "state": 1,
    "warehouse": "0001",
    "tracking_no": "",
    "total_amount": 1550.0,
    "remark": "严聪",
    "customer_name": "王五",
    "creator": "管理员",
    "handler": "",
    "customer_tel": "",
    "shipping_method": "",
    "shipping_tel": "",
    "shipping_addr": "",
    "freight": null,
    "payment_amount": null,
    "salesperson": "",
    "delivery_person": "",
    "customer_type": "",
    "currency": "",
    "price_print": 1,
    "contact_person": "熊贻聪",
    "contact_tel": "18870260862",
    "total_qty": 55.0
  },
  "detail": [
    {
      "product_no": "00143",
      "color": "藏青",
      "sizes": [
        { "size": "XL", "qty": 10 },
        { "size": "L", "qty": 5 }
      ],
      "order_ref": "",
      "brand": "",
      "customer_product_no": "",
      "product_name": "",
      "packaging": "",
      "price": 0,
      "discount": 100,
      "unit": "",
      "remark": ""
    }
  ]
}
```

**main 字段说明**：

| 字段 | 说明 |
|------|------|
| `order_no` | 发货单号 |
| `order_date` | 发货日期 |
| `customer_id` | 客户编号 |
| `customer_addr` | 客户地址 |
| `state` | 0=编辑中，1=已审核 |
| `warehouse` | 发货仓库编号 |
| `tracking_no` | 物流单号 |
| `total_amount` | 总金额 |
| `remark` | 备注 |
| `customer_name` | 客户名称 |
| `creator` | 制单人 |
| `handler` | 经手人 |
| `customer_tel` | 客户电话 |
| `shipping_method` | 托运方式 |
| `shipping_tel` | 托运电话 |
| `shipping_addr` | 托运地址 |
| `freight` | 运费 |
| `payment_amount` | 收款金额 |
| `salesperson` | 业务员 |
| `delivery_person` | 送货人 |
| `customer_type` | 客户类型 |
| `currency` | 币种 |
| `price_print` | 单价打印（1=是，0=否） |
| `contact_person` | 联系人 |
| `contact_tel` | 联系电话 |
| `total_qty` | 总发货数量 |

**detail 字段说明**：

| 字段 | 说明 |
|------|------|
| `product_no` | 货号 |
| `color` | 颜色 |
| `sizes` | 各尺码数量 |
| `order_ref` | 来源订单关联字段 |
| `brand` | 品牌编码 |
| `customer_product_no` | 客户货号 |
| `product_name` | 品名 |
| `packaging` | 包装方式 |
| `price` | 单价 |
| `discount` | 折扣 |
| `unit` | 单位 |
| `remark` | 行备注 |

---

### 5.3 创建发货单

#### `POST /api/sales-shipments`

创建一个新的发货单。

**请求体**：

```json
{
  "customer_id": "0218",
  "shipment_date": "2026-04-14 00:00:00",
  "warehouse": "0001",
  "tracking_no": "SF1234567890",
  "remark": "测试发货单",
  "detail": [
    {
      "product_no": "00001",
      "color": "黑色",
      "sizes": [
        { "size": "L", "qty": 5 },
        { "size": "XL", "qty": 10 }
      ]
    }
  ]
}
```

**字段说明**：

| 字段 | 必填 | 说明 |
|------|------|------|
| `customer_id` | 是 | 客户编号 |
| `shipment_date` | 是 | 发货日期，格式 `YYYY-MM-DD HH:mm:ss` |
| `warehouse` | 是 | 发货仓库编号（如 `0001`） |
| `detail` | 是 | 明细行数组，至少 1 行 |
| `customer_addr` | 否 | 客户地址 |
| `shipping_addr` | 否 | 收货地址 |
| `shipping_tel` | 否 | 收货电话 |
| `shipping_method` | 否 | 运输方式 |
| `delivery_person` | 否 | 送货人 |
| `tracking_no` | 否 | 物流单号 |
| `freight` | 否 | 运费 |
| `salesperson` | 否 | 业务员 |
| `contact_person` | 否 | 联系人 |
| `contact_tel` | 否 | 联系电话 |
| `currency` | 否 | 币种 |
| `customer_type` | 否 | 客户类型 |
| `handler` | 否 | 经手人 |
| `price_print` | 否 | 是否打印单价，`1`=是 `0`=否，默认 1 |
| `payment_amount` | 否 | 收款金额（配合收款功能使用，一般不传） |
| `remark` | 否 | 备注 |

**明细行字段**：

| 字段 | 必填 | 说明 |
|------|------|------|
| `product_no` | 是 | 货号 |
| `color` | 是 | 颜色（发货单的颜色是必填的） |
| `sizes` | 是 | 各尺码数量 |
| `brand` | 否 | 品牌编码 |
| `unit` | 否 | 单位 |
| `price` | 否 | 单价 |
| `discount` | 否 | 折扣，默认 100 |
| `packaging` | 否 | 包装方式 |
| `customer_product_no` | 否 | 客户货号 |
| `order_ref_id` | 否 | 关联的销售订单行 ID |
| `product_spec` | 否 | 货号规格 |
| `semi_product_no` | 否 | 半成品货号 |
| `material` | 否 | 材质 |
| `remark` | 否 | 行备注 |

> 和销售订单的区别：发货单必须填 `warehouse`（仓库）和明细行的 `color`（颜色）。发货单多了 `handler`（经手人）和明细行的 `material`（材质）字段。

**返回示例**（HTTP 201）：

```json
{
  "dh": "20260414-039",
  "message": "保存成功。",
  "state": 0
}
```

---

### 5.4 修改发货单

#### `PUT /api/sales-shipments/{dh}`

修改一个处于编辑中（`state=0`）的发货单。和修改订单一样，只传需要改的字段。

**请求示例**：

```
PUT /api/sales-shipments/20260414-039
```

```json
{
  "remark": "修改后的备注",
  "tracking_no": "SF9999999999"
}
```

**返回示例**：

```json
{
  "dh": "20260414-039",
  "message": "保存成功。",
  "state": 0
}
```

**错误**：已审核的发货单 → 409 `SHIPMENT_NOT_EDITABLE`

---

### 5.5 审核 / 反审 / 作废发货单

#### `POST /api/sales-shipments/{dh}/audit`

和订单的审核操作一样。

**请求体**：

```json
{
  "action": "audit"
}
```

| action 值 | 说明 |
|-----------|------|
| `audit` | 审核 |
| `unaudit` | 反审（撤销审核） |
| `void` | 作废 |

> 和销售订单不同的是，发货单支持**反审**操作（`unaudit`），销售订单也支持但使用场景不同。

---

## 6. 销售对账

### `GET /api/sales-reconciliation`

按客户和日期范围查询对账单，返回汇总信息和逐笔明细。

**参数**：

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `dates` | 是 | 字符串 | 起始日期 |
| `datee` | 是 | 字符串 | 结束日期 |
| `customer_name` | 二选一 | 字符串 | 客户名称（支持模糊匹配，如传 `钟` 可以匹配 `钟江锋`） |
| `customer_id` | 二选一 | 字符串 | 客户编号（精确匹配，如果传了就不用传 customer_name） |

> `customer_name` 和 `customer_id` 至少要传一个。如果客户名匹配到多个人，会返回 422 并列出匹配到的客户供你选择。

**请求示例**：

```
GET /api/sales-reconciliation?customer_name=钟江锋&dates=2026-04-01&datee=2026-04-14
```

**返回示例**：

```json
{
  "summary": {
    "customer_name": "钟江锋",
    "date_from": "2026-04-01",
    "date_to": "2026-04-14",
    "opening_balance": 20524.0,
    "total_shipment": 14066.0,
    "total_return": 0.0,
    "total_payment": 0.0,
    "closing_balance": 34590.0
  },
  "total": 17,
  "rows": [
    {
      "date": "2026-04-01",
      "type": "期初余额",
      "qty": null,
      "amount": null,
      "receivable": 20524.0,
      "received": 0.0,
      "balance": 20524.0,
      "order_no": null
    },
    {
      "date": "2026-04-02",
      "type": "发货",
      "qty": 30.0,
      "amount": 1170.0,
      "receivable": 1170.0,
      "received": 0.0,
      "balance": 21694.0,
      "order_no": "20260402-015"
    }
  ]
}
```

**summary 字段说明**（汇总）：

| 字段 | 说明 |
|------|------|
| `customer_name` | 查询的客户名称 |
| `date_from` / `date_to` | 查询的日期范围 |
| `opening_balance` | 期初余额（这段时间开始前欠多少钱） |
| `total_shipment` | 本期发货金额 |
| `total_return` | 本期退货金额 |
| `total_payment` | 本期收款金额 |
| `closing_balance` | 期末余额（这段时间结束后还欠多少钱） |

**rows 字段说明**（逐笔明细）：

| 字段 | 说明 |
|------|------|
| `date` | 日期 |
| `type` | 类型：`期初余额` / `发货` / `退货` / `收款` / `运费` |
| `qty` | 数量 |
| `amount` | 金额 |
| `receivable` | 应收金额 |
| `received` | 已收金额 |
| `balance` | 应收余额（到这一笔为止还欠多少） |
| `order_no` | 关联的单号 |

**错误示例**：

客户名匹配到多个人：

```json
{
  "error": "AMBIGUOUS_CUSTOMER",
  "message": "客户名 '张' 匹配到多个结果，请使用 customer_id 直接查询: 0100(张三), 0200(张四)"
}
```

---

## 7. 未发货统计报表

### 7.1 查询未发货统计报表

#### `GET /api/unshipped-report`

按日期范围查询销售订单的未发货统计数据。

**参数**：

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `dates` | 是 | 字符串 | 起始日期，如 `2026-04-01` |
| `datee` | 是 | 字符串 | 结束日期，如 `2026-04-15` |
| `customer_id` | 否 | 字符串 | 客户编号过滤 |
| `brand` | 否 | 字符串 | 品牌编号过滤 |
| `product_no` | 否 | 字符串 | 货号过滤 |
| `page` | 否 | 数字 | 页码，默认 1 |
| `rows` | 否 | 数字 | 每页条数，默认 200，最大 5000 |

**返回示例**：

```json
{
  "total": 75,
  "rows": [
    {
      "id": "4D1D7D4C-D5E6-4078-A3C9-4ADD9FDF768D",
      "order_no": "20260414-001",
      "order_date": "2026-04-14",
      "customer_id": "0501",
      "customer_type": "",
      "customer_order_no": "",
      "brand": "0033",
      "product_no": "00143",
      "product_name": "",
      "color": "云舞白",
      "unit": "条",
      "order_qty": 5,
      "shipped_qty": 0,
      "returned_qty": 0,
      "unshipped_qty": 5,
      "unshipped_amount": 0,
      "stock_qty": 272,
      "price": 0,
      "cost_price": 0,
      "tag_price": 0,
      "creator": "客服",
      "remark": "",
      "unshipped_sizes": [
        { "size": "2XL", "qty": 5 }
      ],
      "order_sizes": [
        { "size": "2XL", "qty": 5 }
      ]
    }
  ]
}
```

**rows 字段说明**：

| 字段 | 说明 |
|------|------|
| `id` | 行唯一标识（用于取消/还原操作） |
| `order_no` | 订单号 |
| `order_date` | 订单日期 |
| `customer_id` | 客户编号 |
| `customer_type` | 客户类型 |
| `customer_order_no` | 客户订单号 |
| `brand` | 品牌编码 |
| `product_no` | 货号 |
| `product_name` | 品名 |
| `color` | 颜色 |
| `unit` | 单位 |
| `order_qty` | 订单数量 |
| `shipped_qty` | 已发货数量 |
| `returned_qty` | 退货数量 |
| `unshipped_qty` | 未发货数量 |
| `unshipped_amount` | 未发货金额 |
| `stock_qty` | 库存数量 |
| `price` | 销售单价 |
| `cost_price` | 成本价 |
| `tag_price` | 吊牌价 |
| `creator` | 制单人 |
| `remark` | 备注 |
| `unshipped_sizes` | 未发货各尺码明细 |
| `order_sizes` | 订单各尺码明细 |

---

### 7.2 取消发货

#### `POST /api/unshipped-report/cancel`

将指定报表行标记为"手动完工"（取消发货）。

**请求体**：

```json
{
  "ids": ["4D1D7D4C-D5E6-4078-A3C9-4ADD9FDF768D"]
}
```

| 字段 | 必填 | 说明 |
|------|------|------|
| `ids` | 是 | 报表行 ID 数组，至少 1 个 |

**返回示例**：

```json
{
  "message": "保存成功"
}
```

---

### 7.3 还原订单

#### `POST /api/unshipped-report/restore`

撤销取消发货操作，恢复订单行的发货状态。

**请求体**：与取消发货相同。

```json
{
  "ids": ["4D1D7D4C-D5E6-4078-A3C9-4ADD9FDF768D"]
}
```

**返回示例**：

```json
{
  "message": "保存成功"
}
```

---

## 8. 成品总库存

### `GET /api/inventory`

查询成品仓库的库存总报表。

**参数**：

| 参数 | 必填 | 类型 | 说明 |
|------|------|------|------|
| `warehouse` | 否 | 字符串 | 仓库编号过滤 |
| `product_type` | 否 | 字符串 | 货号类别过滤 |
| `product_no` | 否 | 字符串 | 货号过滤 |
| `product_name` | 否 | 字符串 | 品名模糊匹配 |
| `show_zero` | 否 | 布尔 | 是否显示零库存，默认 false |
| `show_negative` | 否 | 布尔 | 是否显示负库存，默认 false |
| `page` | 否 | 数字 | 页码，默认 1 |
| `rows` | 否 | 数字 | 每页条数，默认 200，最大 5000 |

**返回示例**：

```json
{
  "total": 498,
  "rows": [
    {
      "warehouse": "0001",
      "product_type": "0007",
      "product_no": "00001",
      "product_name": "",
      "material": "",
      "image_url": "",
      "color": "薄荷曼波绿",
      "unit": "条",
      "qty": 437,
      "sale_price": 0,
      "cost_price": 0,
      "amount": 0,
      "in_transit_qty": 0,
      "sizes": [
        { "size": "M", "qty": 26 },
        { "size": "L", "qty": 150 },
        { "size": "XL", "qty": 124 },
        { "size": "2XL", "qty": 51 },
        { "size": "3XL", "qty": 86 }
      ]
    }
  ]
}
```

**rows 字段说明**：

| 字段 | 说明 |
|------|------|
| `warehouse` | 仓库编号 |
| `product_type` | 货号类别 |
| `product_no` | 货号 |
| `product_name` | 品名 |
| `material` | 材质 |
| `image_url` | 图片 URL |
| `color` | 颜色 |
| `unit` | 单位 |
| `qty` | 库存数量（合计） |
| `sale_price` | 销售价 |
| `cost_price` | 成本价 |
| `amount` | 金额 |
| `in_transit_qty` | 生产在途数 |
| `sizes` | 各尺码库存明细 |

---

## 9. 健康检查

### `GET /health`

检查服务是否正常运行。

**返回**：

```json
{ "status": "ok" }
```
