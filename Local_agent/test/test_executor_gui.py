"""
执行模块测试 — tkinter（进程内直调 ExecutorService + 内嵌 SecurityService）。

运行（在 Local_agent 目录下）:
    python test/test_executor_gui.py
    或双击 run_executor_gui.bat

默认 mode=自动路由；可强制指定子能力。侧栏正文不进路由 LLM，有附件时须为写入文件。

本测试会自行挂载 `app.main.security_service`，无需启动 uvicorn。
绿灯/黄灯（未升红）可本地判定；红灯需 Server Center 审批，未连接时会拒绝。
请勿与 `uvicorn app.main:app` 同时写同一份运行时状态（会互相覆盖全局 Service）。
"""

from __future__ import annotations

import asyncio
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

_TEST_DIR = Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent
for p in (_ROOT, _TEST_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from app import main as app_main
from modules.executor.schemas import ExecuteRequest
from modules.executor.service import ExecutorService
from modules.security.service import SecurityService

MODES: list[tuple[str, str]] = [
    ("", "自动路由"),
    ("command", "命令执行"),
    ("read_file", "读取文件"),
    ("write_file", "写入文件"),
    ("delete_file", "删除文件"),
    ("browse_dir", "浏览目录"),
    ("search_file", "搜索文件"),
    ("search_content", "搜索内容"),
    ("codegen", "代码生成"),
]


def _bootstrap_security() -> SecurityService:
    """挂到 app.main，供 local_bus.security_check 使用。"""
    if app_main.security_service is None:
        app_main.security_service = SecurityService(server_client=None)
    return app_main.security_service


class ExecutorGui:
    def __init__(self) -> None:
        self.security = _bootstrap_security()
        self.service = ExecutorService(server_client=None)
        app_main.executor_service = self.service
        self._running = False
        self._loop = asyncio.new_event_loop()

        self.root = tk.Tk()
        self.root.title("Local_agent — 执行模块测试（内嵌安检）")
        self.root.geometry("920x720")
        self.root.minsize(720, 560)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill=tk.X)

        ttk.Label(top, text="mode:").pack(side=tk.LEFT)
        self.mode_var = tk.StringVar(value=" — 自动路由")
        mode_combo = ttk.Combobox(
            top,
            textvariable=self.mode_var,
            values=[f"{mid} — {label}" if mid else f" — {label}" for mid, label in MODES],
            state="readonly",
            width=28,
        )
        mode_combo.current(0)
        mode_combo.pack(side=tk.LEFT, padx=(6, 12))

        self.run_btn = ttk.Button(top, text="执行", command=self._on_run)
        self.run_btn.pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="终止", command=self._on_cancel).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="清空输出", command=self._clear_output).pack(side=tk.LEFT, padx=4)

        ttk.Label(
            self.root,
            text="自然语言（默认自动路由）；下方正文为可选附件。已内嵌安检模块（红灯无 Server Center 时会拒绝）",
            padding=(8, 0),
        ).pack(anchor=tk.W)

        self.action_text = scrolledtext.ScrolledText(
            self.root, height=8, wrap=tk.WORD, font=("Consolas", 10)
        )
        self.action_text.pack(fill=tk.BOTH, expand=False, padx=8, pady=4)
        self.action_text.insert(tk.END, "列出当前目录下的 .py 文件")

        self.file_frame = ttk.LabelFrame(self.root, text="文件正文（可选附件）", padding=6)
        self.file_frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=4)
        self.file_content = scrolledtext.ScrolledText(
            self.file_frame, height=6, wrap=tk.WORD, font=("Consolas", 10)
        )
        self.file_content.pack(fill=tk.BOTH, expand=True)

        out_frame = ttk.LabelFrame(self.root, text="执行结果", padding=6)
        out_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.output = scrolledtext.ScrolledText(
            out_frame, height=16, wrap=tk.WORD, font=("Consolas", 10)
        )
        self.output.pack(fill=tk.BOTH, expand=True)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(
            fill=tk.X, side=tk.BOTTOM
        )

    def _selected_mode(self) -> str | None:
        raw = self.mode_var.get().split(" — ", 1)[0].strip()
        return raw or None

    def _append_output(self, text: str) -> None:
        self.output.insert(tk.END, text + "\n")
        self.output.see(tk.END)

    def _clear_output(self) -> None:
        self.output.delete("1.0", tk.END)

    def _set_busy(self, busy: bool) -> None:
        self._running = busy
        self.run_btn.config(state=tk.DISABLED if busy else tk.NORMAL)

    def _on_run(self) -> None:
        action = self.action_text.get("1.0", tk.END).strip()
        if not action:
            messagebox.showwarning("提示", "请输入动作描述")
            return
        if self._running:
            return

        mode = self._selected_mode()
        file_body = self.file_content.get("1.0", tk.END)
        file_content = file_body if file_body.strip() else None
        mode_label = mode or "auto"

        self._set_busy(True)
        self.status_var.set(f"执行中 ({mode_label})…")
        self._append_output(f"\n--- 提交 mode={mode_label} ---\n{action[:200]}")

        def worker() -> None:
            try:
                result = self._loop.run_until_complete(
                    self.service.execute(
                        ExecuteRequest(
                            action_text=action,
                            mode=mode,  # type: ignore[arg-type]
                            caller_module="test_executor_gui",
                            purpose="GUI 独立测试",
                            file_content=file_content,
                        )
                    )
                )
                self.root.after(0, lambda r=result: self._show_result(r))
            except Exception as exc:
                self.root.after(0, lambda e=exc: self._show_error(e))

        threading.Thread(target=worker, daemon=True).start()

    def _show_result(self, result) -> None:
        self._set_busy(False)
        lines = [
            f"ok: {result.ok}",
            f"job_id: {result.job_id}",
            f"action_type: {result.action_type}",
            f"error: {result.error}",
            f"reason: {result.reason}",
            f"exit_code: {result.exit_code}",
            f"duration_ms: {result.duration_ms}",
        ]
        if result.security:
            lines.append(
                f"security: allowed={result.security.allowed} "
                f"risk={result.security.risk_level} reason={result.security.reason}"
            )
        if result.stdout:
            lines.append("\n[stdout]\n" + result.stdout)
        if result.stderr:
            lines.append("\n[stderr]\n" + result.stderr)
        self._append_output("\n".join(lines))
        self.status_var.set("完成" if result.ok else f"失败: {result.reason or result.error}")

    def _show_error(self, exc: Exception) -> None:
        self._set_busy(False)
        self._append_output(f"\n[异常] {exc}")
        self.status_var.set("异常")
        messagebox.showerror("执行异常", str(exc))

    def _on_cancel(self) -> None:
        result = self.service.cancel_job(None)
        msg = (
            f"已请求终止 job_id={result.get('job_id')}"
            if result.get("ok")
            else result.get("reason", "无运行中任务")
        )
        self.status_var.set(msg)
        self._append_output(f"\n[终止] {msg}")

    def _on_close(self) -> None:
        try:
            self.service.cancel_job(None)
        except Exception:
            pass
        if app_main.executor_service is self.service:
            app_main.executor_service = None
        if app_main.security_service is self.security:
            app_main.security_service = None
        self._loop.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    ExecutorGui().run()


if __name__ == "__main__":
    main()
