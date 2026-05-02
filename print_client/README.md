# ERP 配货单自动打印客户端

独立运行在连接打印机的 Windows 电脑上，自动从 ERP 服务器获取待打印的配货单并发送到本地打印机。

## 安装依赖

```bash
pip install requests pywin32
```

可选（推荐）：安装 [SumatraPDF](https://www.sumatrapdfreader.org/download-free-pdf-viewer) 以获得最佳静默打印效果。

如需打印测试页功能，额外安装：

```bash
pip install reportlab
```

## 使用方法

```bash
python print_client.py
```

1. 填写 ERP 服务器地址（如 `http://192.168.1.100:8000`）
2. 填写登录账号和密码
3. 点击「测试连接并登录」确认连接正常
4. 选择本地打印机，可点击「打印测试页」验证
5. 点击「保存配置」，配置会保存到本地 `print_client_config.json`
6. 点击「▶ 启动监听」开始自动打印

## 工作原理

```
ERP 系统 (审核下单/替换旧单)
    ↓ 生成 PDF → 加入 print_queue 表
打印客户端 (本程序)
    ↓ 轮询 GET /api/printer/queue/poll
    ↓ 下载 GET /api/printer/queue/download/{path}
    ↓ 本地打印 (SumatraPDF / ShellExecute)
    ↓ 回报 POST /api/printer/queue/ack
```

## 配置文件

`print_client_config.json` 示例：

```json
{
  "server_url": "http://192.168.1.100:8000",
  "username": "admin",
  "password": "your_password",
  "printer_name": "HP LaserJet Pro",
  "poll_interval": 5
}
```

- `server_url` — ERP 服务器地址
- `username` / `password` — ERP 系统登录凭证
- `printer_name` — 本地打印机名称
- `poll_interval` — 轮询间隔（秒），默认 5 秒
