"""
ERP 配货单自动打印客户端
独立运行在连接打印机的 Windows 电脑上，轮询服务器获取待打印任务并自动打印。

依赖安装:
    pip install requests pywin32

推荐安装 SumatraPDF 以获得最佳静默打印效果:
    https://www.sumatrapdfreader.org/download-free-pdf-viewer
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

# ---------------------------------------------------------------------------
# 日志
# ---------------------------------------------------------------------------
LOG_FMT = "[%(asctime)s] %(levelname)s  %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FMT)
logger = logging.getLogger("PrintClient")

# ---------------------------------------------------------------------------
# 配置文件路径（与 exe 同目录或用户目录）
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))))
CONFIG_PATH = _SCRIPT_DIR / "print_client_config.json"

DEFAULT_CONFIG = {
    "server_url": "",
    "username": "",
    "password": "",
    "printer_name": "",
    "poll_interval": 5,
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return {**DEFAULT_CONFIG, **cfg}
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 打印机枚举
# ---------------------------------------------------------------------------
def list_printers() -> list[str]:
    try:
        import win32print
        default = ""
        try:
            default = win32print.GetDefaultPrinter()
        except Exception:
            pass
        printers = []
        for p in win32print.EnumPrinters(2, None, 2):
            printers.append(p["pPrinterName"])
        # 将默认打印机放到首位
        if default and default in printers:
            printers.remove(default)
            printers.insert(0, default)
        return printers
    except ImportError:
        logger.error("win32print 不可用，请安装 pywin32: pip install pywin32")
        return []


def get_default_printer() -> str:
    try:
        import win32print
        return win32print.GetDefaultPrinter()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# PDF 打印
# ---------------------------------------------------------------------------
def _find_sumatra() -> str | None:
    candidates = [
        r"C:\Program Files\SumatraPDF\SumatraPDF.exe",
        r"C:\Program Files (x86)\SumatraPDF\SumatraPDF.exe",
        os.path.expanduser(r"~\AppData\Local\SumatraPDF\SumatraPDF.exe"),
    ]
    for p in candidates:
        if os.path.isfile(p):
            return p
    return shutil.which("SumatraPDF") or shutil.which("SumatraPDF.exe")


def print_pdf(pdf_bytes: bytes, printer_name: str) -> None:
    """将 PDF 发送到打印机，失败抛异常"""
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, prefix="erp_print_")
    try:
        tmp.write(pdf_bytes)
        tmp.flush()
        tmp_path = tmp.name
        tmp.close()

        # 方式1: SumatraPDF 静默打印
        sumatra = _find_sumatra()
        if sumatra:
            cmd = [sumatra, "-print-to", printer_name, "-silent", tmp_path]
            logger.info("SumatraPDF: %s", " ".join(cmd))
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
            if proc.returncode == 0:
                logger.info("打印成功 (SumatraPDF)")
                return
            logger.warning("SumatraPDF 失败 (code=%d)", proc.returncode)

        # 方式2: ShellExecute
        try:
            import win32api
            win32api.ShellExecute(0, "printto", tmp_path, f'"{printer_name}"', ".", 0)
            logger.info("打印成功 (ShellExecute)")
            return
        except Exception as e:
            logger.warning("ShellExecute 失败: %s", e)

        raise RuntimeError("无法打印，请安装 SumatraPDF 或系统 PDF 阅读器")
    finally:
        threading.Thread(target=lambda: (time.sleep(30), _safe_remove(tmp_path)), daemon=True).start()


def _safe_remove(path: str):
    try:
        os.unlink(path)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# API 客户端
# ---------------------------------------------------------------------------
class ERPPrintAPI:
    def __init__(self, server_url: str):
        self.base = server_url.rstrip("/")
        self.token: str = ""
        self.session = requests.Session()

    def login(self, username: str, password: str) -> bool:
        url = f"{self.base}/api/auth/login"
        try:
            r = self.session.post(url, json={"username": username, "password": password}, timeout=10)
            r.raise_for_status()
            data = r.json()
            self.token = data.get("data", {}).get("access_token") or data.get("access_token", "")
            if self.token:
                self.session.headers["Authorization"] = f"Bearer {self.token}"
                return True
            return False
        except Exception as e:
            logger.error("登录失败: %s", e)
            return False

    def poll_jobs(self) -> list[dict]:
        try:
            r = self.session.get(f"{self.base}/api/printer/queue/poll?limit=10", timeout=10)
            r.raise_for_status()
            return r.json().get("data", [])
        except Exception as e:
            logger.error("轮询失败: %s", e)
            return []

    def download_pdf(self, object_path: str) -> bytes | None:
        try:
            r = self.session.get(f"{self.base}/api/printer/queue/download/{object_path}", timeout=30)
            r.raise_for_status()
            return r.content
        except Exception as e:
            logger.error("下载 PDF 失败: %s", e)
            return None

    def ack_job(self, job_id: int, success: bool, error: str = ""):
        try:
            self.session.post(
                f"{self.base}/api/printer/queue/ack",
                json={"job_id": job_id, "success": success, "error": error},
                timeout=10,
            )
        except Exception as e:
            logger.error("回报结果失败: %s", e)


# ---------------------------------------------------------------------------
# GUI 应用
# ---------------------------------------------------------------------------
class PrintClientApp:
    def __init__(self):
        self.cfg = load_config()
        self.api: ERPPrintAPI | None = None
        self.running = False
        self.poll_thread: threading.Thread | None = None
        self.logged_in = False

        self.root = tk.Tk()
        self.root.title("ERP 配货单打印客户端")
        self.root.geometry("620x580")
        self.root.resizable(False, False)

        self._build_ui()
        self._load_config_to_ui()

    # ---- UI 构建 ----
    def _build_ui(self):
        root = self.root

        # 服务器配置
        frame_srv = ttk.LabelFrame(root, text=" 服务器连接 ", padding=10)
        frame_srv.pack(fill="x", padx=12, pady=(10, 6))

        ttk.Label(frame_srv, text="服务器地址:").grid(row=0, column=0, sticky="w", pady=3)
        self.entry_url = ttk.Entry(frame_srv, width=45)
        self.entry_url.grid(row=0, column=1, columnspan=2, sticky="we", pady=3, padx=(6, 0))

        ttk.Label(frame_srv, text="用户名:").grid(row=1, column=0, sticky="w", pady=3)
        self.entry_user = ttk.Entry(frame_srv, width=20)
        self.entry_user.grid(row=1, column=1, sticky="we", pady=3, padx=(6, 0))

        ttk.Label(frame_srv, text="密码:").grid(row=2, column=0, sticky="w", pady=3)
        self.entry_pass = ttk.Entry(frame_srv, width=20, show="*")
        self.entry_pass.grid(row=2, column=1, sticky="we", pady=3, padx=(6, 0))

        btn_frame = ttk.Frame(frame_srv)
        btn_frame.grid(row=3, column=0, columnspan=3, pady=(6, 0))
        self.btn_login = ttk.Button(btn_frame, text="测试连接并登录", command=self._on_login)
        self.btn_login.pack(side="left", padx=4)
        self.btn_save = ttk.Button(btn_frame, text="保存配置", command=self._on_save)
        self.btn_save.pack(side="left", padx=4)

        self.lbl_login_status = ttk.Label(frame_srv, text="未连接", foreground="gray")
        self.lbl_login_status.grid(row=3, column=2, sticky="e", pady=(6, 0))

        frame_srv.columnconfigure(1, weight=1)

        # 打印机选择
        frame_ptr = ttk.LabelFrame(root, text=" 打印机 ", padding=10)
        frame_ptr.pack(fill="x", padx=12, pady=6)

        ttk.Label(frame_ptr, text="选择打印机:").grid(row=0, column=0, sticky="w")
        self.cmb_printer = ttk.Combobox(frame_ptr, state="readonly", width=40)
        self.cmb_printer.grid(row=0, column=1, sticky="we", padx=(6, 0))
        self.btn_refresh_ptr = ttk.Button(frame_ptr, text="刷新", command=self._refresh_printers, width=8)
        self.btn_refresh_ptr.grid(row=0, column=2, padx=(6, 0))

        self.btn_test_print = ttk.Button(frame_ptr, text="打印测试页", command=self._on_test_print)
        self.btn_test_print.grid(row=1, column=1, sticky="w", padx=(6, 0), pady=(6, 0))

        frame_ptr.columnconfigure(1, weight=1)

        # 轮询间隔
        frame_poll = ttk.LabelFrame(root, text=" 轮询设置 ", padding=10)
        frame_poll.pack(fill="x", padx=12, pady=6)

        ttk.Label(frame_poll, text="轮询间隔 (秒):").grid(row=0, column=0, sticky="w")
        self.spin_interval = ttk.Spinbox(frame_poll, from_=2, to=60, width=6)
        self.spin_interval.grid(row=0, column=1, sticky="w", padx=(6, 0))

        # 启动/停止按钮
        frame_ctrl = ttk.Frame(root)
        frame_ctrl.pack(fill="x", padx=12, pady=6)

        self.btn_start = ttk.Button(frame_ctrl, text="▶ 启动监听", command=self._on_start)
        self.btn_start.pack(side="left", padx=4)
        self.btn_stop = ttk.Button(frame_ctrl, text="■ 停止", command=self._on_stop, state="disabled")
        self.btn_stop.pack(side="left", padx=4)

        self.lbl_status = ttk.Label(frame_ctrl, text="就绪", foreground="gray")
        self.lbl_status.pack(side="right", padx=4)

        # 日志区域
        frame_log = ttk.LabelFrame(root, text=" 日志 ", padding=6)
        frame_log.pack(fill="both", expand=True, padx=12, pady=(6, 10))

        self.txt_log = tk.Text(frame_log, height=10, font=("Consolas", 9), state="disabled", bg="#1e1e1e", fg="#d4d4d4")
        scrollbar = ttk.Scrollbar(frame_log, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=scrollbar.set)
        self.txt_log.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

    # ---- 配置读写 ----
    def _load_config_to_ui(self):
        self.entry_url.insert(0, self.cfg.get("server_url", ""))
        self.entry_user.insert(0, self.cfg.get("username", ""))
        self.entry_pass.insert(0, self.cfg.get("password", ""))
        self.spin_interval.delete(0, "end")
        self.spin_interval.insert(0, str(self.cfg.get("poll_interval", 5)))
        self._refresh_printers()
        saved = self.cfg.get("printer_name", "")
        if saved and saved in self.cmb_printer["values"]:
            self.cmb_printer.set(saved)

    def _collect_config(self) -> dict:
        return {
            "server_url": self.entry_url.get().strip(),
            "username": self.entry_user.get().strip(),
            "password": self.entry_pass.get().strip(),
            "printer_name": self.cmb_printer.get().strip(),
            "poll_interval": int(self.spin_interval.get() or 5),
        }

    def _on_save(self):
        self.cfg = self._collect_config()
        save_config(self.cfg)
        self._log("配置已保存到 " + str(CONFIG_PATH))

    # ---- 打印机 ----
    def _refresh_printers(self):
        printers = list_printers()
        self.cmb_printer["values"] = printers
        if printers:
            current = self.cmb_printer.get()
            if current not in printers:
                self.cmb_printer.current(0)
        self._log(f"检测到 {len(printers)} 台打印机")

    def _on_test_print(self):
        printer = self.cmb_printer.get()
        if not printer:
            messagebox.showwarning("提示", "请先选择打印机")
            return
        try:
            pdf_bytes = _generate_test_page(printer)
            print_pdf(pdf_bytes, printer)
            self._log(f"✅ 测试页已发送到: {printer}")
            messagebox.showinfo("成功", f"测试页已发送到 {printer}")
        except Exception as e:
            self._log(f"❌ 测试打印失败: {e}")
            messagebox.showerror("失败", str(e))

    # ---- 登录 ----
    def _on_login(self):
        cfg = self._collect_config()
        if not cfg["server_url"]:
            messagebox.showwarning("提示", "请输入服务器地址")
            return
        if not cfg["username"] or not cfg["password"]:
            messagebox.showwarning("提示", "请输入用户名和密码")
            return

        self._log(f"正在连接 {cfg['server_url']} ...")
        self.api = ERPPrintAPI(cfg["server_url"])
        ok = self.api.login(cfg["username"], cfg["password"])
        if ok:
            self.logged_in = True
            self.lbl_login_status.config(text="已连接 ✓", foreground="green")
            self._log("✅ 登录成功")
        else:
            self.logged_in = False
            self.lbl_login_status.config(text="连接失败", foreground="red")
            self._log("❌ 登录失败，请检查地址/账号/密码")

    # ---- 轮询控制 ----
    def _on_start(self):
        if not self.logged_in:
            self._on_login()
            if not self.logged_in:
                return

        printer = self.cmb_printer.get()
        if not printer:
            messagebox.showwarning("提示", "请先选择打印机")
            return

        # 保存当前配置
        self.cfg = self._collect_config()
        save_config(self.cfg)

        self.running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.lbl_status.config(text="监听中...", foreground="green")
        self._log(f"▶ 开始监听，打印机: {printer}，间隔: {self.cfg['poll_interval']}s")

        self.poll_thread = threading.Thread(target=self._poll_loop, daemon=True)
        self.poll_thread.start()

    def _on_stop(self):
        self.running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.lbl_status.config(text="已停止", foreground="gray")
        self._log("■ 已停止监听")

    def _poll_loop(self):
        while self.running:
            try:
                jobs = self.api.poll_jobs()
                if jobs:
                    self._log(f"📋 获取到 {len(jobs)} 个待打印任务")
                for job in jobs:
                    if not self.running:
                        break
                    self._process_job(job)
            except Exception as e:
                self._log(f"轮询异常: {e}")

            interval = self.cfg.get("poll_interval", 5)
            for _ in range(interval * 2):
                if not self.running:
                    return
                time.sleep(0.5)

    def _process_job(self, job: dict):
        job_id = job["id"]
        order_no = job["order_no"]
        pdf_obj = job["pdf_object"]
        printer = self.cmb_printer.get()
        attempts = job.get("attempts", 0)

        self._log(f"🖨️  处理任务 #{job_id}: 订单 {order_no} (第{attempts + 1}次)")

        # 下载 PDF
        pdf_bytes = self.api.download_pdf(pdf_obj)
        if not pdf_bytes:
            self.api.ack_job(job_id, False, "下载 PDF 失败")
            self._log(f"❌ #{job_id} 下载 PDF 失败")
            return

        # 打印（失败重试 2 次）
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                print_pdf(pdf_bytes, printer)
                self.api.ack_job(job_id, True)
                self._log(f"✅ #{job_id} 订单 {order_no} 打印成功 (第{attempt}次)")
                return
            except Exception as e:
                self._log(f"⚠️  #{job_id} 第{attempt}次打印失败: {e}")
                if attempt < max_retries:
                    time.sleep(2)

        self.api.ack_job(job_id, False, str(f"打印失败 ({max_retries}次)"))
        self._log(f"❌ #{job_id} 订单 {order_no} 最终打印失败")

    # ---- 日志 ----
    def _log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        logger.info(msg)

        def _append():
            self.txt_log.config(state="normal")
            self.txt_log.insert("end", line)
            self.txt_log.see("end")
            self.txt_log.config(state="disabled")

        self.root.after(0, _append)

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# 测试页生成
# ---------------------------------------------------------------------------
def _generate_test_page(printer_name: str) -> bytes:
    """用纯 Python 生成一个简单的测试页 PDF"""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import mm
        import io

        buf = io.BytesIO()
        c = canvas.Canvas(buf, pagesize=A4)
        w, h = A4

        c.setFont("Helvetica-Bold", 24)
        c.drawCentredString(w / 2, h - 60, "ERP Printer Test Page")
        c.setFont("Helvetica", 14)
        c.drawCentredString(w / 2, h - 100, f"Printer: {printer_name}")
        c.drawCentredString(w / 2, h - 125, f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        c.setFont("Helvetica", 12)
        y = h - 180
        for line in [
            "This is a test page from the ERP Print Client.",
            "If you can see this page clearly, your printer is working correctly.",
            "",
            "  - Text: ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            "  - Numbers: 0123456789",
            "  - Paper: A4 (210mm x 297mm)",
        ]:
            c.drawString(60, y, line)
            y -= 20

        c.setStrokeColorRGB(0, 0, 0)
        c.setLineWidth(0.5)
        margin = 15 * mm
        c.rect(margin, margin, w - 2 * margin, h - 2 * margin)
        c.showPage()
        c.save()
        return buf.getvalue()
    except ImportError:
        # reportlab 不可用时生成极简 PDF
        return _minimal_test_pdf(printer_name)


def _minimal_test_pdf(printer_name: str) -> bytes:
    """不依赖 reportlab 的极简 PDF"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    content = f"ERP Print Client Test Page\nPrinter: {printer_name}\nTime: {now}\nIf you can read this, printing works."
    # 极简 PDF 1.4
    objs = []
    objs.append(b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj")
    objs.append(b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj")
    objs.append(b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj")
    stream = b"BT /F1 14 Tf 50 780 Td (" + content.replace("\n", ")Tj 0 -20 Td (").encode() + b")Tj ET"
    objs.append(b"4 0 obj<</Length " + str(len(stream)).encode() + b">>stream\n" + stream + b"\nendstream\nendobj")
    objs.append(b"5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj")

    body = b"%PDF-1.4\n"
    offsets = []
    for obj in objs:
        offsets.append(len(body))
        body += obj + b"\n"
    xref_offset = len(body)
    body += b"xref\n0 6\n0000000000 65535 f \n"
    for off in offsets:
        body += f"{off:010d} 00000 n \n".encode()
    body += f"trailer<</Size 6/Root 1 0 R>>\nstartxref\n{xref_offset}\n%%EOF".encode()
    return body


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app = PrintClientApp()
    app.run()
