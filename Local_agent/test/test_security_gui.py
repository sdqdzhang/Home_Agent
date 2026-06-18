"""
安全检查模块测试 — tkinter 可视化（需 Server Center）。

运行（在 Local_agent 目录下）:
    python test/test_security_gui.py

前提:
  1. Server Center 已启动（默认 http://127.0.0.1:8765）
  2. 先点「连接 Server Center」
  3. 红色命令需在 Web UI 左侧「安全检查模块」中批准/拒绝
  4. 请勿与 `uvicorn app.main:app` 同时运行（同一客户端 ID 会冲突）

黄色命令需本地 Ollama 模型（security.judge 槽位）。
"""

from __future__ import annotations

import asyncio
import json
import sys
import threading
import time
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

_TEST_DIR = Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent
for p in (_ROOT, _TEST_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common import LogPanel, ROOT

# 预制测试命令
PRESET_GREEN = [
    ("绿 · 白命令 ls", "ls", "查看当前目录"),
    ("绿 · 白命令 pwd", "pwd", ""),
    ("绿 · 白命令 cat README", "cat README.md", "查看项目说明"),
]

PRESET_RED = [
    ("红 · 黑目录 keys", "cat Local_agent/keys/test.pem", "尝试读取密钥目录"),
    ("红 · 黑目录 .env", "type Local_agent\\.env", "尝试读取环境变量文件"),
    ("红 · 黑命令+非白目录", "rm -rf C:/Windows/Temp_test_agent", "危险删除系统路径"),
]

PRESET_YELLOW = [
    ("黄 · 黑命令+白目录", "rm data/agent_workspace/temp.log", "清理工作区临时文件"),
    ("黄 · 网络黑命令", "curl https://example.com", "测试网络请求"),
    ("黄 · 未分类写操作", "copy notes.txt data/agent_workspace/out.txt", "复制到工作区"),
]


class AsyncRuntime:
    """后台常驻 asyncio 循环，供 WebSocket 与 check 共用。"""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._loop is not None:
            return

        def _run() -> None:
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        while self._loop is None:
            time.sleep(0.01)

    def run(self, coro, *, timeout: float | None = None):
        if self._loop is None:
            raise RuntimeError("AsyncRuntime 未启动")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def schedule(self, coro) -> None:
        if self._loop is None:
            raise RuntimeError("AsyncRuntime 未启动")
        asyncio.run_coroutine_threadsafe(coro, self._loop)


class SecurityTestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("安全检查模块测试")
        self.geometry("980x820")
        self.minsize(860, 700)
        self._runtime = AsyncRuntime()
        self._runtime.start()
        self._service = None
        self._server_client = None
        self._server_url_cached = ""
        self._listeners: list = []
        self._connected = False
        self._connecting = False
        self._build()
        self._log(f"项目根目录: {ROOT}")
        self._log("四列表位置: modules/security/lists/*.txt")
        self._log("请先连接 Server Center，再运行测试命令")

    def _build(self) -> None:
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)

        srv = ttk.LabelFrame(frm, text="Server Center（必填）", padding=6)
        srv.pack(fill="x", pady=4)
        row_srv = ttk.Frame(srv)
        row_srv.pack(fill="x")
        ttk.Label(row_srv, text="地址").pack(side="left")
        self.server_url = tk.StringVar(value="http://127.0.0.1:8765")
        ttk.Entry(row_srv, textvariable=self.server_url, width=50).pack(side="left", padx=4)
        self.connect_btn = ttk.Button(row_srv, text="连接", command=self._on_connect)
        self.connect_btn.pack(side="left", padx=4)
        self.conn_label = ttk.Label(srv, text="未连接", foreground="gray")
        self.conn_label.pack(anchor="w", pady=2)

        custom = ttk.LabelFrame(frm, text="自定义检查", padding=6)
        custom.pack(fill="x", pady=4)
        row_cmd = ttk.Frame(custom)
        row_cmd.pack(fill="x", pady=2)
        ttk.Label(row_cmd, text="命令").pack(side="left")
        self.command_var = tk.StringVar(value="ls")
        ttk.Entry(row_cmd, textvariable=self.command_var, width=70).pack(side="left", padx=4)
        row_purpose = ttk.Frame(custom)
        row_purpose.pack(fill="x", pady=2)
        ttk.Label(row_purpose, text="目的").pack(side="left")
        self.purpose_var = tk.StringVar(value="")
        ttk.Entry(row_purpose, textvariable=self.purpose_var, width=70).pack(side="left", padx=4)
        ttk.Button(custom, text="执行检查", command=self._on_custom_check).pack(anchor="w", pady=4)

        presets = ttk.Notebook(frm)
        presets.pack(fill="x", pady=4)
        for title, items, color in [
            ("一定绿", PRESET_GREEN, "#2d6a4f"),
            ("一定红", PRESET_RED, "#9b2226"),
            ("黄色(模型)", PRESET_YELLOW, "#ca6702"),
        ]:
            tab = ttk.Frame(presets, padding=4)
            presets.add(tab, text=title)
            for label, cmd, purpose in items:
                row = ttk.Frame(tab)
                row.pack(fill="x", pady=2)
                ttk.Button(
                    row,
                    text=label,
                    command=lambda c=cmd, p=purpose: self._run_check(c, p),
                ).pack(side="left")
                ttk.Label(row, text=cmd, font=("Consolas", 9)).pack(side="left", padx=8)

        ttk.Label(frm, text="输出").pack(anchor="w")
        self.log = LogPanel(frm)
        self.log.pack(fill="both", expand=True, pady=4)

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def _on_err(self, err: str) -> None:
        self.after(0, lambda: self._log(f"!!! 错误:\n{err}"))

    async def _connect_async(self, url: str):
        from app.config import settings
        from modules.security import MODULE_ID, MODULE_NAME
        from modules.security.service import SecurityService
        from shared.server_center import ServerCenterClient, WebSocketListener, ensure_client_keys

        if not url:
            raise ValueError("请填写 Server Center 地址")

        if self._server_client and self._server_url_cached == url and self._service:
            health = await self._server_client.ping()
            return health

        for listener in self._listeners:
            await listener.stop()
        self._listeners.clear()

        pk, pub = ensure_client_keys(settings.keys_dir, settings.rsa_key_size)
        client = ServerCenterClient(url, "安全检查模块", pk, pub, id_prefix="security")
        health = await client.ping()
        await client.ensure_registered()

        service = SecurityService(server_client=client)

        async def handler(data):
            await service.handle_ws_event(data)

        for channel in (MODULE_ID, MODULE_NAME):
            listener = WebSocketListener(url, channel)
            listener.on_message(handler)
            await listener.start()
            self._listeners.append(listener)

        self._server_client = client
        self._server_url_cached = url
        self._service = service
        return health

    def _on_connect(self) -> None:
        if self._connecting:
            return
        url = self.server_url.get().strip().rstrip("/")
        self._connecting = True
        self.connect_btn.configure(state="disabled")
        self._log(">>> 连接 Server Center...")

        def _ok(health):
            self.after(0, lambda: self._on_connect_ok(health))

        def _run():
            try:
                health = self._runtime.run(self._connect_async(url), timeout=60)
                _ok(health)
            except Exception:
                self.after(0, lambda: self._on_connect_fail(traceback.format_exc()))

        threading.Thread(target=_run, daemon=True).start()

    def _on_connect_ok(self, health) -> None:
        self._connecting = False
        self._connected = True
        self.connect_btn.configure(state="normal")
        self.conn_label.configure(text="已连接", foreground="green")
        self._log(f"<<< 连接成功 health={json.dumps(health, ensure_ascii=False)}")

    def _on_connect_fail(self, err: str) -> None:
        self._connecting = False
        self._connected = False
        self.connect_btn.configure(state="normal")
        self.conn_label.configure(text="连接失败", foreground="red")
        self._log(f"!!! 连接失败:\n{err}")

    def _require_connected(self) -> bool:
        if not self._connected or not self._service:
            messagebox.showwarning("未连接", "请先连接 Server Center")
            return False
        return True

    def _on_custom_check(self) -> None:
        self._run_check(self.command_var.get(), self.purpose_var.get())

    def _run_check(self, command: str, purpose: str) -> None:
        if not self._require_connected():
            return
        self._log(f">>> 检查: {command!r} purpose={purpose!r}")

        async def _coro():
            from modules.security.schemas import CheckRequest

            return await self._service.check(
                CheckRequest(command=command, purpose=purpose, caller_module="test_gui")
            )

        def _ok(result):
            self.after(0, lambda: self._log_result(result))

        def _run():
            try:
                result = self._runtime.run(_coro())
                _ok(result)
            except Exception:
                self._on_err(traceback.format_exc())

        threading.Thread(target=_run, daemon=True).start()

    def _log_result(self, result) -> None:
        if hasattr(result, "model_dump"):
            data = result.model_dump()
        else:
            data = dict(result)
        level = data.get("risk_level", "?")
        allowed = data.get("allowed")
        self._log(f"<<< 结果 risk={level} allowed={allowed}")
        self._log(json.dumps(data, ensure_ascii=False, indent=2))
        if level == "red" and data.get("approval_id"):
            self._log("    → 若仍在等待，请在 Web UI「安全检查模块」中审批")
        if allowed:
            self._log("    ✓ 可以执行（本测试不实际执行命令）")


if __name__ == "__main__":
    app = SecurityTestApp()
    app.mainloop()
