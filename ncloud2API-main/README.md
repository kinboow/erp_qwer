# ncloud2API

弘兆云 ERP（ncloud2）HTTP API 封装服务，基于 FastAPI，模拟浏览器会话与 ERP 后端通信。

## 项目结构

```
ncloud2API/
├── app.py                  # uvicorn 入口（转发至 app/main.py）
├── app/
│   ├── main.py             # FastAPI 应用实例、lifespan
│   ├── config.py           # pydantic-settings 配置（读取 .env）
│   ├── dependencies.py     # FastAPI Depends 工厂函数
│   ├── exceptions.py       # 全局异常类与 handler
│   ├── client/
│   │   ├── erp_auth.py     # ERP 登录 / 会话管理
│   │   └── erp_client.py   # 异步 HTTP 客户端（自动重登）
│   ├── routers/            # 路由层（一文件对应一资源）
│   │   ├── auth.py
│   │   ├── base.py
│   │   ├── sales_orders.py
│   │   ├── shipments.py
│   │   ├── reconciliation.py
│   │   ├── unshipped_report.py
│   │   └── inventory.py
│   ├── services/           # 业务逻辑层
│   │   ├── base.py
│   │   ├── sales_orders.py
│   │   ├── shipments.py
│   │   ├── reconciliation.py
│   │   ├── unshipped_report.py
│   │   └── inventory.py
│   └── schemas/            # Pydantic 响应模型
│       ├── base.py
│       ├── sales_orders.py
│       ├── shipments.py
│       ├── reconciliation.py
│       ├── unshipped_report.py
│       ├── inventory.py
│       └── erp_raw/        # ERP 原始响应 schema（extra="ignore"）
│           ├── sales_orders.py
│           ├── shipments.py
│           ├── unshipped_report.py
│           └── inventory.py
├── smoke_test.py           # 本地联调脚本（覆盖全部接口）
├── requirements.txt        # Python 依赖
├── docs/
│   └── requirements/       # 需求文档与参考截图
│       ├── 需求说明.md
│       ├── 需求表.xlsx
│       └── extracted_img_*.png
└── wecom-temp-*.jpg        # 账套二维码图片（登录用）
```

## 接口一览

### 基础

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/health` | 健康检查 |
| POST | `/api/login` | 登录 ERP，返回账套信息 |
| GET | `/api/account-set` | 获取账套信息 |
| GET | `/api/products` | 获取货号列表 |

### 销售订单

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sales-orders` | 获取销售订单列表（规范化字段） |
| GET | `/api/sales-orders/{dh}` | 获取销售订单详情（25 主表字段 + 12 明细字段） |
| POST | `/api/sales-orders` | 创建销售订单 |
| PUT | `/api/sales-orders/{dh}` | 修改销售订单（仅编辑态） |
| POST | `/api/sales-orders/{dh}/audit` | 审核/反审/作废销售订单 |

### 销售发货单

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sales-shipments` | 获取发货单列表（规范化字段） |
| GET | `/api/sales-shipments/{dh}` | 获取发货单详情（26 主表字段 + 12 明细字段） |
| POST | `/api/sales-shipments` | 创建发货单 |
| PUT | `/api/sales-shipments/{dh}` | 修改发货单（仅编辑态） |
| POST | `/api/sales-shipments/{dh}/audit` | 审核/反审/作废发货单 |

### 销售对账

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/sales-reconciliation` | 获取销售对账单（按客户+日期范围） |

### 未发货统计报表

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/unshipped-report` | 查询未发货统计报表（按日期范围） |
| POST | `/api/unshipped-report/cancel` | 取消发货（标记手动完工） |
| POST | `/api/unshipped-report/restore` | 还原订单（撤销取消发货） |

### 成品总库存

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/inventory` | 查询成品总库存（按仓库/货号/颜色） |

## 接口参数说明

> 详细字段说明和返回示例见 [docs/api-reference.md](docs/api-reference.md)。

### `GET /api/sales-orders`
| 参数 | 必填 | 说明 |
|------|------|------|
| `dates` | ✅ | 起始日期，如 `2026-04-01` |
| `datee` | ✅ | 结束日期，如 `2026-04-14` |
| `state` | | 状态筛选，默认 `["0","1"]` |
| `rows` | | 每页行数，默认 20 |
| `page` | | 页码，默认 1 |

返回 `{total, rows}`，每行包含 `order_no`、`order_date`、`customer_id`、`customer_name`、`state`、`creator`、`salesperson`、`total_qty`、`total_amount` 等 13 个规范化字段。

### `POST /api/sales-orders`
| 字段 | 必填 | 说明 |
|------|------|------|
| `customer_id` | ✅ | 客户编号 |
| `order_date` | ✅ | 订单日期 `YYYY-MM-DD HH:mm:ss` |
| `detail` | ✅ | 明细行数组（至少 1 行），每行含 `product_no`、`sizes[{size, qty}]` |
| `customer_addr` | | 客户地址 |
| `remark` | | 备注 |
| `salesperson` | | 业务员 |
| `order_ref` | | 客户订单号（ERP: ddh） |

### `PUT /api/sales-orders/{dh}`

仅限 `state=0`（编辑态）的订单。所有字段可选，传入的字段会覆盖原值。

### `POST /api/sales-orders/{dh}/audit`
| 字段 | 必填 | 说明 |
|------|------|------|
| `action` | ✅ | `audit`（审核）/ `unaudit`（反审）/ `void`（作废） |

### `GET /api/sales-shipments`
| 参数 | 必填 | 说明 |
|------|------|------|
| `dates` | ✅ | 起始日期 |
| `datee` | ✅ | 结束日期 |
| `state` | | 状态筛选，默认 `["0","1"]` |
| `rows` | | 每页行数，默认 20 |
| `page` | | 页码，默认 1 |

返回 `{total, rows}`，每行包含 `order_no`、`order_date`、`customer_id`、`customer_name`、`state`、`salesperson`、`tracking_no`、`shipping_method`、`freight` 等 14 个规范化字段。

### `POST /api/sales-shipments`
| 字段 | 必填 | 说明 |
|------|------|------|
| `customer_id` | ✅ | 客户编号 |
| `shipment_date` | ✅ | 发货日期 `YYYY-MM-DD HH:mm:ss` |
| `warehouse` | ✅ | 发货仓库编号 |
| `detail` | ✅ | 明细行数组，每行含 `product_no`、`color`（必填）、`sizes[{size, qty}]` |
| `tracking_no` | | 物流单号 |
| `remark` | | 备注 |

### `PUT /api/sales-shipments/{dh}`

仅限 `state=0`（编辑态）的发货单。所有字段可选。

### `POST /api/sales-shipments/{dh}/audit`
| 字段 | 必填 | 说明 |
|------|------|------|
| `action` | ✅ | `audit`（审核）/ `unaudit`（反审）/ `void`（作废） |

### `GET /api/sales-reconciliation`
| 参数 | 必填 | 说明 |
|------|------|------|
| `dates` | ✅ | 起始日期 |
| `datee` | ✅ | 结束日期 |
| `customer_name` | ✅ (二选一) | 客户名称（模糊匹配） |
| `customer_id` | ✅ (二选一) | 客户 ID（精确匹配，优先于 customer_name） |

响应包含 `summary`（汇总：期初余额、发货金额、退货金额、已收款、期末余额）和 `rows`（明细行）。

### `GET /api/unshipped-report`
| 参数 | 必填 | 说明 |
|------|------|------|
| `dates` | ✅ | 起始日期 |
| `datee` | ✅ | 结束日期 |
| `customer_id` | | 客户编号过滤 |
| `brand` | | 品牌编号过滤 |
| `product_no` | | 货号过滤 |
| `page` | | 页码，默认 1 |
| `rows` | | 每页条数，默认 200 |

返回 `{total, rows}`，每行包含 `id`、`order_no`、`order_date`、`customer_id`、`product_no`、`color`、`order_qty`、`shipped_qty`、`unshipped_qty`、`unshipped_amount`、`stock_qty`、`unshipped_sizes`、`order_sizes` 等 24 个字段。

### `POST /api/unshipped-report/cancel`
| 字段 | 必填 | 说明 |
|------|------|------|
| `ids` | ✅ | 报表行 ID 数组（至少 1 个），来自查询结果的 `id` 字段 |

### `POST /api/unshipped-report/restore`

与取消发货参数相同，传入 `ids` 数组。

### `GET /api/inventory`
| 参数 | 必填 | 说明 |
|------|------|------|
| `warehouse` | | 仓库编号过滤 |
| `product_type` | | 货号类别过滤 |
| `product_no` | | 货号过滤 |
| `product_name` | | 品名模糊匹配 |
| `show_zero` | | 是否显示零库存，默认 false |
| `show_negative` | | 是否显示负库存，默认 false |
| `page` | | 页码，默认 1 |
| `rows` | | 每页条数，默认 200 |

返回 `{total, rows}`，每行包含 `warehouse`、`product_no`、`color`、`qty`、`sizes`、`sale_price`、`cost_price`、`in_transit_qty` 等 14 个字段。

## 安装依赖

```bash
python3 -m pip install -r requirements.txt
```

## 启动服务

```bash
uvicorn app:app --reload
```

启动后访问 `http://127.0.0.1:8000/docs` 查看接口文档。

## 配置

通过 `.env` 文件或环境变量覆盖默认配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NCLOUD_BASE_URL` | `http://nclouddl43.ywhzsoft.com:8154` | ERP 服务地址 |
| `NCLOUD_USERNAME` | `测试` | 登录账号 |
| `NCLOUD_PASSWORD` | `123` | 登录密码 |
| `NCLOUD_QR_IMAGE_PATH` | `./wecom-temp-*.jpg` | 账套二维码图片路径 |

## 本地自测

```bash
python3 smoke_test.py
```

脚本会依次调用全部 Read 接口并打印响应，需要能访问 ERP 服务。Write 接口（创建/修改/审核）请使用测试客户（ID: `0218`，名称: 测试）手动验证。
