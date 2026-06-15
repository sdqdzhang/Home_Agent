"""
LLM 调用测试 — 简易 tkinter 窗口。

运行（在 Local_agent 目录下）:
    python test/test_llm_gui.py

前置: Ollama 已启动且已拉取 LA_LLM_MODEL 对应模型。
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

# 引导路径：支持 python test/test_llm_gui.py 直接运行
_TEST_DIR = Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent
for p in (_ROOT, _TEST_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common import LogPanel, ROOT, run_async


class LLMTestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LLM 调用测试")
        self.geometry("720x520")
        self._build()
        self._log(f"项目根目录: {ROOT}")
        self._log("填写 Base URL / 模型后点击「发送」测试。")

    def _build(self) -> None:
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)

        row1 = ttk.Frame(frm)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="Base URL").pack(side="left")
        self.base_url = tk.StringVar(value="http://127.0.0.1:11434/v1")
        ttk.Entry(row1, textvariable=self.base_url, width=50).pack(side="left", padx=4)

        row2 = ttk.Frame(frm)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="Model").pack(side="left")
        self.model = tk.StringVar(value="llama3.2")
        ttk.Entry(row2, textvariable=self.model, width=24).pack(side="left", padx=4)
        ttk.Label(row2, text="API Key").pack(side="left", padx=(12, 0))
        self.api_key = tk.StringVar(value="ollama")
        ttk.Entry(row2, textvariable=self.api_key, width=16).pack(side="left", padx=4)

        ttk.Label(frm, text="用户消息").pack(anchor="w", pady=(8, 0))
        self.prompt = tk.Text(frm, height=4, font=("Microsoft YaHei UI", 10))
        self.prompt.pack(fill="x")
        self.prompt.insert("1.0", "用一句话介绍你自己。")

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=6)
        self.send_btn = ttk.Button(btns, text="发送（普通）", command=self._on_send)
        self.send_btn.pack(side="left")
        self.json_btn = ttk.Button(btns, text="发送（JSON 模式）", command=self._on_send_json)
        self.json_btn.pack(side="left", padx=6)
        ttk.Button(btns, text="清空日志", command=self._clear).pack(side="left")

        ttk.Label(frm, text="输出").pack(anchor="w")
        self.log = LogPanel(frm)
        self.log.pack(fill="both", expand=True, pady=4)

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def _clear(self) -> None:
        self.log.clear()

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.send_btn.configure(state=state)
        self.json_btn.configure(state=state)

    def _make_client(self):
        from shared.llm.client import LLMClient
        from shared.llm.config import LLMSettings

        cfg = LLMSettings(
            base_url=self.base_url.get().strip(),
            api_key=self.api_key.get().strip(),
            model=self.model.get().strip(),
        )
        return LLMClient(cfg)

    def _on_send(self) -> None:
        text = self.prompt.get("1.0", "end").strip()
        if not text:
            return
        self._set_busy(True)
        self._log(f">>> 普通对话: {text[:80]}...")

        def coro():
            client = self._make_client()
            return client.chat([{"role": "user", "content": text}])

        run_async(coro, self._on_ok, self._on_err)

    def _on_send_json(self) -> None:
        text = self.prompt.get("1.0", "end").strip()
        if not text:
            return
        self._set_busy(True)
        self._log(f">>> JSON 模式: {text[:80]}...")

        def coro():
            client = self._make_client()
            return client.chat_json(
                [
                    {"role": "system", "content": "只输出合法 JSON 对象。"},
                    {"role": "user", "content": f"请用 JSON 回答，包含 reply 字段：{text}"},
                ]
            )

        run_async(coro, self._on_ok_json, self._on_err)

    def _on_ok(self, reply: str) -> None:
        self.after(0, lambda: (self._set_busy(False), self._log(f"<<< {reply}")))

    def _on_ok_json(self, data: dict) -> None:
        self.after(0, lambda: (self._set_busy(False), self._log(f"<<< JSON:\n{json.dumps(data, ensure_ascii=False, indent=2)}")))

    def _on_err(self, err: str) -> None:
        self.after(0, lambda: (self._set_busy(False), self._log(f"!!! 错误:\n{err}")))


if __name__ == "__main__":
    app = LLMTestApp()
    app.mainloop()
