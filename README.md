# 工厂智能化管理系统

基于 **Python FastAPI + Vue3** 的前后端分离工厂管理系统。

## 技术栈

### 后端
- **框架**: FastAPI
- **数据库**: MySQL 8.0
- **ORM**: SQLAlchemy
- **缓存**: Redis 7
- **消息队列**: RabbitMQ 3
- **对象存储**: 阿里云OSS / MinIO
- **认证**: JWT

### 前端
- **框架**: Vue 3 + Vite
- **UI组件**: Element Plus
- **状态管理**: Pinia
- **路由**: Vue Router
- **HTTP客户端**: Axios

## 功能特性

- ✅ 用户认证与授权（JWT）
- ✅ RBAC权限管理系统
- ✅ 用户管理（增删改查）
- ✅ 角色管理
- ✅ 权限管理
- ✅ Redis缓存
- ✅ OSS文件存储
- ✅ RabbitMQ消息队列
- ✅ 响应式前端界面

## 项目结构

```
erp/
├── backend/                 # Python后端
│   ├── app/
│   │   ├── routers/        # 路由
│   │   ├── models.py       # 数据模型
│   │   ├── schemas.py      # Pydantic模型
│   │   ├── database.py     # 数据库连接
│   │   ├── dependencies.py # 依赖注入
│   │   ├── config.py       # 配置
│   │   └── utils/          # 工具类
│   ├── main.py             # 应用入口
│   ├── requirements.txt    # Python依赖
│   └── .env.example        # 环境变量模板
├── frontend/               # Vue3前端
│   ├── src/
│   │   ├── api/           # API接口
│   │   ├── views/         # 页面组件
│   │   ├── layouts/       # 布局组件
│   │   ├── stores/        # Pinia状态管理
│   │   ├── router/        # 路由配置
│   │   └── utils/         # 工具类
│   ├── package.json
│   └── vite.config.js
├── database/
│   └── schema.sql         # 数据库结构
└── docker-compose.yml     # Docker配置
```

## 快速开始

### 1. 启动Docker服务

启动 MySQL、Redis、RabbitMQ、MinIO：

```bash
docker-compose up -d
```

### 2. 后端启动

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 复制环境变量
cp .env.example .env

# 启动服务
python main.py
```

后端服务运行在 `http://localhost:8000`

### 3. 前端启动

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端服务运行在 `http://localhost:3000`

## Docker服务访问

- **MySQL**: localhost:3306
  - 用户名: root
  - 密码: root123456
  - 数据库: factory_management

- **Redis**: localhost:6379
  - 密码: redis123456

- **RabbitMQ管理界面**: http://localhost:15672
  - 用户名: admin
  - 密码: admin123456

- **MinIO控制台**: http://localhost:9001
  - 用户名: minioadmin
  - 密码: minioadmin123

## 默认账号

- 用户名: `admin`
- 密码: `admin123`

## API文档

后端启动后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 主要API接口

### 认证接口
- `POST /api/auth/login` - 用户登录
- `POST /api/auth/logout` - 退出登录
- `GET /api/auth/userinfo` - 获取用户信息

### 用户管理接口
- `GET /api/users` - 获取用户列表
- `GET /api/users/{id}` - 获取用户详情
- `POST /api/users` - 创建用户
- `PUT /api/users/{id}` - 更新用户
- `DELETE /api/users/{id}` - 删除用户

## 开发说明

### 后端开发

```bash
# 开发模式（自动重载）
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 前端开发

```bash
# 开发模式
npm run dev

# 构建生产版本
npm run build

# 预览生产构建
npm run preview
```

## 权限系统

系统采用RBAC（基于角色的访问控制）模型：

- **用户（User）**: 系统使用者
- **角色（Role）**: 权限的集合
- **权限（Permission）**: 具体的操作权限

权限类型：
- 菜单权限（type=1）
- 按钮权限（type=2）
- 接口权限（type=3）

## 部署说明

### 后端部署

```bash
# 使用gunicorn部署
pip install gunicorn
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

### 前端部署

```bash
# 构建
npm run build

# dist目录部署到Nginx或其他Web服务器
```

## 注意事项

1. 生产环境请修改所有默认密码
2. JWT_SECRET_KEY 必须使用强密码
3. 建议使用阿里云OSS，MinIO仅用于开发测试
4. Redis密码在生产环境必须设置
5. 定期备份MySQL数据库
6. 前端代理配置在 `vite.config.js` 中修改

## License

MIT
