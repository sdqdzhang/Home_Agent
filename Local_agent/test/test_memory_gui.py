"""
记忆模块测试 — tkinter：observe / recall / reflect / 工作记忆 / 核心记忆。

运行（在 Local_agent 目录下）:
    python test/test_memory_gui.py

依赖:
  - Ollama: llama3.2（memory.assess / memory.reflect）
  - Ollama: nomic-embed-text（memory.embed）
  - 若 llm.db 已存在且无 memory 槽位，请在模型配置 UI 绑定或删除 data/llm.db 后重启以 seed
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

_TEST_DIR = Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent
for p in (_ROOT, _TEST_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common import LogPanel, ROOT, run_async


class MemoryTestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("记忆模块测试")
        self.geometry("960x780")
        self.minsize(820, 640)
        self._service = None
        self._build()
        self._log(f"项目根目录: {ROOT}")
        self._log("提示: 先 Observe 写入观察，Recall 三维检索，Reflect 需 Ollama llama3.2")

    def _get_service(self):
        if self._service is None:
            from modules.memory.service import MemoryService

            self._service = MemoryService(server_client=None)
        return self._service

    def _build(self) -> None:
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)

        status_frm = ttk.LabelFrame(frm, text="状态", padding=6)
        status_frm.pack(fill="x", pady=4)
        row = ttk.Frame(status_frm)
        row.pack(fill="x")
        ttk.Button(row, text="刷新状态", command=self._on_status).pack(side="left")
        self.status_var = tk.StringVar(value="（未加载）")
        ttk.Label(row, textvariable=self.status_var).pack(side="left", padx=8)

        observe_frm = ttk.LabelFrame(frm, text="Observe — 观察写入（自动打分 + 归档）", padding=6)
        observe_frm.pack(fill="x", pady=4)
        self.observe_text = tk.Text(observe_frm, height=4, wrap="word")
        self.observe_text.pack(fill="x", pady=2)
        self.observe_text.insert("1.0", "用户今天询问了 Python 异步爬虫的实现方式")
        btn_row = ttk.Frame(observe_frm)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="写入 Observe", command=self._on_observe).pack(side="left")
        for label, text in [
            (" mundane", "整理了桌面文件"),
            (" medium", "用户偏好使用深色主题 IDE"),
            (" high", "用户批准了 rm 清理工作区临时文件的命令"),
        ]:
            ttk.Button(btn_row, text=label, command=lambda t=text: self._fill_observe(t)).pack(side="left", padx=2)

        recall_frm = ttk.LabelFrame(frm, text="Recall — 三维加权检索", padding=6)
        recall_frm.pack(fill="x", pady=4)
        rq = ttk.Frame(recall_frm)
        rq.pack(fill="x")
        ttk.Label(rq, text="查询").pack(side="left")
        self.recall_query = tk.StringVar(value="Python 爬虫")
        ttk.Entry(rq, textvariable=self.recall_query, width=50).pack(side="left", padx=4)
        ttk.Button(rq, text="检索", command=self._on_recall).pack(side="left")

        ctx_frm = ttk.LabelFrame(frm, text="Context — 工作记忆上下文（供 LLM）", padding=6)
        ctx_frm.pack(fill="x", pady=4)
        ttk.Button(ctx_frm, text="获取 /memory/context", command=self._on_context).pack(anchor="w")

        reflect_frm = ttk.LabelFrame(frm, text="Reflect — 多对一融合（删旧流水账 → 写一条 insight）", padding=6)
        reflect_frm.pack(fill="x", pady=4)
        rr = ttk.Frame(reflect_frm)
        rr.pack(fill="x")
        ttk.Label(rr, text="limit").pack(side="left")
        self.reflect_limit = tk.IntVar(value=10)
        ttk.Spinbox(rr, from_=1, to=20, textvariable=self.reflect_limit, width=5).pack(side="left", padx=4)
        ttk.Button(rr, text="触发 Reflect", command=self._on_reflect).pack(side="left", padx=4)

        core_frm = ttk.LabelFrame(frm, text="Core Memory — 手动核心记忆", padding=6)
        core_frm.pack(fill="x", pady=4)
        cr = ttk.Frame(core_frm)
        cr.pack(fill="x")
        ttk.Label(cr, text="key").pack(side="left")
        self.core_key = tk.StringVar(value="user_theme")
        ttk.Entry(cr, textvariable=self.core_key, width=16).pack(side="left", padx=4)
        ttk.Label(cr, text="value").pack(side="left")
        self.core_value = tk.StringVar(value="深色主题")
        ttk.Entry(cr, textvariable=self.core_value, width=30).pack(side="left", padx=4)
        ttk.Button(cr, text="写入 Core", command=self._on_core_upsert).pack(side="left", padx=4)
        ttk.Button(cr, text="列出 Core", command=self._on_core_list).pack(side="left")

        log_frm = ttk.LabelFrame(frm, text="输出", padding=6)
        log_frm.pack(fill="both", expand=True, pady=4)
        self.log = LogPanel(log_frm)
        self.log.pack(fill="both", expand=True)

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def _fill_observe(self, text: str) -> None:
        self.observe_text.delete("1.0", "end")
        self.observe_text.insert("1.0", text)

    def _on_status(self) -> None:
        svc = self._get_service()
        st = svc.status()
        self.status_var.set(
            f"工作记忆 {st.working_count}/{st.working_max_size} · "
            f"Archive {st.archive_count} · Core {st.core_count}"
        )
        self._log(json.dumps(st.model_dump(), ensure_ascii=False, indent=2))

    def _on_observe(self) -> None:
        content = self.observe_text.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("提示", "请输入观察内容")
            return

        def coro():
            return self._get_service().observe({"content": content})

        run_async(coro, self._on_observe_done, self._on_error)

    def _on_observe_done(self, result) -> None:
        self._log("=== Observe ===")
        self._log(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        self._on_status()

    def _on_recall(self) -> None:
        query = self.recall_query.get().strip()
        if not query:
            return
        result = self._get_service().recall({"query": query})
        self._on_recall_done(result)

    def _on_recall_done(self, result) -> None:
        self._log("=== Recall ===")
        self._log(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))

    def _on_context(self) -> None:
        ctx = self._get_service().get_context()
        self._log("=== Context ===")
        self._log(json.dumps(ctx, ensure_ascii=False, indent=2))

    def _on_reflect(self) -> None:
        limit = int(self.reflect_limit.get())

        def coro():
            return self._get_service().reflect({"limit": limit})

        run_async(coro, self._on_reflect_done, self._on_error)

    def _on_reflect_done(self, result) -> None:
        self._log("=== Reflect ===")
        self._log(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        if not result.success:
            messagebox.showwarning("反思未写入", result.reason or "失败")
        self._on_status()

    def _on_core_upsert(self) -> None:
        row = self._get_service().upsert_core(
            {"key": self.core_key.get().strip(), "value": self.core_value.get().strip()}
        )
        self._log("=== Core upsert ===")
        self._log(json.dumps(row.model_dump(), ensure_ascii=False, indent=2))
        self._on_status()

    def _on_core_list(self) -> None:
        items = self._get_service().list_core()
        self._log("=== Core list ===")
        self._log(json.dumps([i.model_dump() for i in items], ensure_ascii=False, indent=2))

    def _on_error(self, err: str) -> None:
        self._log("=== ERROR ===")
        self._log(err)
        messagebox.showerror("错误", err[:800])


def main() -> None:
    app = MemoryTestApp()
    app.mainloop()


if __name__ == "__main__":
    main()
