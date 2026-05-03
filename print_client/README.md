# ERP 配货单打印客户端

独立运行在连接打印机的 Windows 电脑上，轮询服务器获取待打印任务并自动打印。

## 快速开始

1. 运行 `ERP打印客户端.exe`（每台电脑只能开一个）
2. 输入服务器 IP 地址（端口固定 8900，无需登录）
3. 点击「测试连接」
4. 选择本地打印机
5. 点击「启动监听」

客户端会自动轮询服务器获取待打印任务，下载 PDF 后发送到所选打印机。

## 特性

- **无需登录** — 只需输入服务器 IP 即可连接
- **单实例** — 每台电脑只允许运行一个客户端
- **心跳上报** — 前端可实时查看客户端在线/离线状态
- **自动重试** — 打印失败自动重试最多 3 次

## 依赖（仅源码运行时需要）

```bash
pip install requests pywin32
```

推荐安装 [SumatraPDF](https://www.sumatrapdfreader.org/download-free-pdf-viewer) 以获得最佳静默打印效果。

## 配置文件

配置保存在 `print_client_config.json`（与 EXE 同目录），下次启动自动加载。

```json
{
  "server_ip": "192.168.1.100",
  "printer_name": "HP LaserJet Pro",
  "poll_interval": 5
}
```

- `server_ip` — 服务器 IP 地址（端口固定 8900）
- `printer_name` — 本地打印机名称
- `poll_interval` — 轮询间隔（秒），默认 5 秒

## 打包为 EXE

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name "ERP打印客户端" --hidden-import win32print --hidden-import win32api print_client.py
```

输出文件在 `dist/ERP打印客户端.exe`。
