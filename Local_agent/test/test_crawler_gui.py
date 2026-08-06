"""
网页爬取测试 — 简易 tkinter 窗口，可切换「使用模型 / 不使用模型」。

运行（在 Local_agent 目录下）:
    python test/test_crawler_gui.py

不使用模型: 仅引擎规则 + 过滤器最高分，无需 Ollama。
使用模型:   完整流程（判断、调参、择优、兜底），需要 Ollama。
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


class CrawlerTestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("网页爬取测试")
        self.geometry("800x600")
        self._build()
        self._log(f"项目根目录: {ROOT}")
        self._log("模式说明:")
        self._log("  [不使用模型] 自适应引擎 → 引擎 success → 过滤器最高分")
        self._log("  [使用模型]   上述 + LLM 判断/调参/择优/兜底（需 Ollama）")

    def _build(self) -> None:
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)

        row1 = ttk.Frame(frm)
        row1.pack(fill="x", pady=2)
        ttk.Label(row1, text="URL").pack(side="left")
        self.url = tk.StringVar(value="https://example.com")
        ttk.Entry(row1, textvariable=self.url, width=70).pack(side="left", padx=4)

        row2 = ttk.Frame(frm)
        row2.pack(fill="x", pady=2)
        ttk.Label(row2, text="任务描述").pack(side="left")
        self.task = tk.StringVar(value="提取页面标题和正文")
        ttk.Entry(row2, textvariable=self.task, width=60).pack(side="left", padx=4)

        row3 = ttk.Frame(frm)
        row3.pack(fill="x", pady=4)
        self.use_model = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="使用模型（LLM 判断与过滤）", variable=self.use_model).pack(side="left")
        self.ignore_ssl = tk.BooleanVar(value=False)
        ttk.Checkbutton(row3, text="忽略 SSL 证书错误", variable=self.ignore_ssl).pack(side="left", padx=(8, 0))
        ttk.Label(row3, text="  预设 URL:").pack(side="left", padx=(12, 0))
        ttk.Button(row3, text="example.com", command=lambda: self.url.set("https://example.com")).pack(side="left", padx=2)
        ttk.Button(row3, text="httpbin", command=lambda: self.url.set("https://httpbin.org/html")).pack(side="left", padx=2)

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=4)
        self.run_btn = ttk.Button(btns, text="开始爬取", command=self._on_run)
        self.run_btn.pack(side="left")
        ttk.Button(btns, text="清空日志", command=self._clear).pack(side="left", padx=6)

        ttk.Label(frm, text="输出").pack(anchor="w")
        self.log = LogPanel(frm)
        self.log.pack(fill="both", expand=True, pady=4)

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def _clear(self) -> None:
        self.log.clear()

    def _on_run(self) -> None:
        url = self.url.get().strip()
        if not url:
            return
        use_model = self.use_model.get()
        task = self.task.get().strip()
        ignore_ssl = self.ignore_ssl.get()
        mode = "使用模型" if use_model else "不使用模型"
        self.run_btn.configure(state="disabled")
        self._log(f">>> [{mode}] {url}")
        self._log(f"    任务: {task}")
        if ignore_ssl:
            self._log("    已启用: 忽略 SSL 证书错误")
        if use_model:
            self._log("    提示: 使用模型时 LLM 每次调用约 30-90 秒，下方会实时输出进度")

        def _on_log_line(line: str) -> None:
            self.after(0, lambda l=line: self._log(f"    | {l}"))

        async def _coro():
            from modules.crawler.config import crawler_settings
            from modules.crawler.model import CrawlerAssistant
            from modules.crawler.pipeline import CrawlOrchestrator
            from modules.crawler.storage import JobStore

            crawler_settings.data_dir.mkdir(parents=True, exist_ok=True)
            store = JobStore(
                crawler_settings.db_path,
                crawler_settings.artifacts_dir,
                crawler_settings.texts_dir,
            )
            orch = CrawlOrchestrator(store, CrawlerAssistant())
            config = {"verify_ssl": not ignore_ssl}
            return await orch.run(
                url,
                task=task,
                config=config,
                use_model=use_model,
                log_callback=_on_log_line,
            )

        run_async(_coro, self._on_ok, self._on_err)

    def _on_ok(self, outcome: dict) -> None:
        def show():
            self.run_btn.configure(state="normal")
            self._log(f"<<< success={outcome.get('success')} job_id={outcome.get('job_id')}")
            self._log(f"    title={outcome.get('title', '')}")
            self._log(f"    log_path={outcome.get('log_path', '')}")
            result = outcome.get("result") or {}
            if result:
                self._log(f"    mode={result.get('mode')} strategy={result.get('strategy')}")
                content = result.get("content", "")
                preview = content[:1200] + ("..." if len(content) > 1200 else "")
                self._log(f"    content:\n{preview}")
                self._log(f"    filters={json.dumps(result.get('filters', []), ensure_ascii=False)}")
            for line in outcome.get("log", [])[-15:]:
                self._log(f"    | {line}")

        self.after(0, show)

    def _on_err(self, err: str) -> None:
        self.after(0, lambda: (self.run_btn.configure(state="normal"), self._log(f"!!! 错误:\n{err}")))


if __name__ == "__main__":
    app = CrawlerTestApp()
    app.mainloop()
