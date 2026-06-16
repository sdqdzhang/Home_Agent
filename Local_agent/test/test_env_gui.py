"""
环境感知测试 — tkinter 窗口，可切换「使用模型 / 不使用模型」。

运行（在 Local_agent 目录下）:
    python test/test_env_gui.py

推送测试前提:
  1. Server Center 已启动（默认 http://127.0.0.1:8765）
  2. 勾选「推送到 Server Center」并先点「测试连接」
  3. 采集/总结后，在 Web UI 左侧点击「环境感知模块」查看消息
     （system_status 为静默消息，不会出现在主对话频道）
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

_TEST_DIR = Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent
for p in (_ROOT, _TEST_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common import LogPanel, ROOT, run_async


class EnvTestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("环境感知测试")
        self.geometry("920x720")
        self._service = None
        self._server_client = None
        self._server_url_cached = ""
        self._build()
        self._log(f"项目根目录: {ROOT}")
        self._log("提示: 推送成功后请在 Web UI 左侧进入「环境感知模块」频道查看")

    def _build(self) -> None:
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)

        srv = ttk.LabelFrame(frm, text="Server Center", padding=6)
        srv.pack(fill="x", pady=4)
        row_srv = ttk.Frame(srv)
        row_srv.pack(fill="x")
        ttk.Label(row_srv, text="地址").pack(side="left")
        self.server_url = tk.StringVar(value="http://127.0.0.1:8765")
        ttk.Entry(row_srv, textvariable=self.server_url, width=55).pack(side="left", padx=4)
        ttk.Button(row_srv, text="测试连接", command=self._on_test_connection).pack(side="left", padx=4)
        self.push_server = tk.BooleanVar(value=False)
        ttk.Checkbutton(srv, text="采集/总结时推送到 Server Center", variable=self.push_server).pack(anchor="w", pady=4)

        row = ttk.Frame(frm)
        row.pack(fill="x", pady=4)
        self.use_model = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="使用模型（LLM 运营总结 / 对话）", variable=self.use_model).pack(side="left")

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=4)
        self.collect_btn = ttk.Button(btns, text="采集一次", command=self._on_collect)
        self.collect_btn.pack(side="left")
        ttk.Button(btns, text="执行压缩总结", command=self._on_summary).pack(side="left", padx=6)
        ttk.Button(btns, text="读取 /env/status", command=self._on_status).pack(side="left", padx=6)
        ttk.Button(btns, text="清空日志", command=self._clear).pack(side="left", padx=6)

        ttk.Label(frm, text="输出").pack(anchor="w")
        self.log = LogPanel(frm)
        self.log.pack(fill="both", expand=True, pady=4)

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def _clear(self) -> None:
        self.log.clear()

    def _invalidate_server(self) -> None:
        self._server_client = None
        self._server_url_cached = ""

    async def _build_server_client_async(self):
        from app.config import settings
        from shared.server_center import ServerCenterClient, ensure_client_keys

        url = self.server_url.get().strip().rstrip("/")
        if not url:
            raise ValueError("请填写 Server Center 地址")
        if self._server_client and self._server_url_cached == url:
            health = await self._server_client.ping()
            return self._server_client, health

        pk, pub = ensure_client_keys(settings.keys_dir, settings.rsa_key_size)
        client = ServerCenterClient(url, "环境感知模块", pk, pub, id_prefix="env")
        health = await client.ping()
        await client.ensure_registered()
        self._server_client = client
        self._server_url_cached = url
        return client, health

    def _get_or_create_service(self, server=None):
        from modules.env.service import EnvService

        if self._service is None:
            self._service = EnvService(server_client=server)
        else:
            self._service.server = server
        self._service.use_model = self.use_model.get()
        return self._service

    def _on_test_connection(self) -> None:
        self._log(">>> 测试 Server Center 连接...")

        async def _coro():
            return await self._build_server_client_async()

        def _ok(result):
            client, health = result
            self.after(0, lambda: self._log(f"<<< 连接成功: {client.base_url}\n    health={json.dumps(health, ensure_ascii=False)}"))

        run_async(_coro, _ok, self._on_err)

    def _on_collect(self) -> None:
        self.collect_btn.configure(state="disabled")
        push = self.push_server.get()
        self._log(f">>> 采集一次... push={push}")

        async def _coro():
            server = None
            if push:
                server, _ = await self._build_server_client_async()
            svc = self._get_or_create_service(server)
            return await svc.collect_once(push=push)

        run_async(_coro, self._on_collect_ok, self._on_err)

    def _on_collect_ok(self, outcome: dict) -> None:
        def show():
            self.collect_btn.configure(state="normal")
            snapshot = outcome.get("snapshot") or outcome
            self._log("<<< 采集完成")
            self._log(json.dumps(snapshot, ensure_ascii=False, indent=2)[:4000])
            push = outcome.get("push")
            if push:
                self._log_push_result(push)
            elif self.push_server.get():
                self._log("!!! 推送未执行（可能未连接 Server Center）")

        self.after(0, show)

    def _log_push_result(self, push: dict) -> None:
        msg = push.get("message") or {}
        chunks = push.get("_encrypted_chunks")
        plain_bytes = push.get("_plaintext_bytes")
        self._log(
            f"[推送成功] id={msg.get('id')} module={push.get('module')} "
            f"chunks={chunks} bytes={plain_bytes}"
        )
        self._log("    → 请打开 Web UI 左侧「环境感知模块」查看 system_status 消息")

    def _on_summary(self) -> None:
        push = self.push_server.get()
        self._log(f">>> 执行压缩总结... push={push} model={self.use_model.get()}")

        async def _coro():
            server = None
            if push:
                server, _ = await self._build_server_client_async()
            svc = self._get_or_create_service(server)
            return await svc.run_summary(push=push, use_model=self.use_model.get())

        run_async(_coro, self._on_summary_ok, self._on_err)

    def _on_summary_ok(self, result: dict) -> None:
        def show():
            self._log("<<< 总结完成")
            self._log(json.dumps(result, ensure_ascii=False, indent=2)[:6000])

        self.after(0, show)

    def _on_status(self) -> None:
        svc = self._get_or_create_service()
        payload = svc.status_payload
        self._log("--- GET /env/status 等效数据 ---")
        self._log(json.dumps(payload, ensure_ascii=False, indent=2)[:6000])

    def _on_err(self, err: str) -> None:
        self.after(0, lambda: (self.collect_btn.configure(state="normal"), self._log(f"!!! 错误:\n{err}")))


if __name__ == "__main__":
    app = EnvTestApp()
    app.mainloop()
