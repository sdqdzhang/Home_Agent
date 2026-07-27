"""
处理模块测试 — tkinter：左侧输入要求与 DataBlock 列表，右侧显示输出块。

运行（在 Local_agent 目录下）:
    python test/test_processor_gui.py
    或双击 run_processor_gui.bat

进程内直调 ProcessorService，无需启动 uvicorn。
需要已配置 LLM（Ollama / 绑定 processor.process 槽位）。
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

_TEST_DIR = Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent
for p in (_ROOT, _TEST_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common import run_async
from modules.processor.ids import IdCounter
from modules.processor.schemas import DataBlock, ProcessRequest
from modules.processor.service import ProcessorService

UI_ID_PREFIX = "ui"


class AddBlockDialog(tk.Toplevel):
    """弹窗：填写 type / content / producer / metadata。"""

    def __init__(self, master: tk.Tk) -> None:
        super().__init__(master)
        self.title("添加 DataBlock")
        self.geometry("520x420")
        self.minsize(420, 360)
        self.transient(master)
        self.grab_set()
        self.result: DataBlock | None = None

        frm = ttk.Frame(self, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        row_type = ttk.Frame(frm)
        row_type.pack(fill=tk.X, pady=2)
        ttk.Label(row_type, text="type", width=10).pack(side=tk.LEFT)
        self.type_var = tk.StringVar(value="code")
        ttk.Entry(row_type, textvariable=self.type_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        row_prod = ttk.Frame(frm)
        row_prod.pack(fill=tk.X, pady=2)
        ttk.Label(row_prod, text="producer", width=10).pack(side=tk.LEFT)
        self.producer_var = tk.StringVar(value="ui")
        ttk.Entry(row_prod, textvariable=self.producer_var).pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(frm, text="content").pack(anchor=tk.W, pady=(8, 2))
        self.content = scrolledtext.ScrolledText(frm, height=10, wrap=tk.WORD, font=("Consolas", 10))
        self.content.pack(fill=tk.BOTH, expand=True)
        self.content.insert(tk.END, "print('hello')")

        ttk.Label(frm, text="metadata（JSON 对象，可空）").pack(anchor=tk.W, pady=(8, 2))
        self.meta = scrolledtext.ScrolledText(frm, height=4, wrap=tk.WORD, font=("Consolas", 10))
        self.meta.pack(fill=tk.BOTH, expand=False)
        self.meta.insert(tk.END, '{\n  "language": "python"\n}')

        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btns, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="添加", command=self._on_ok).pack(side=tk.RIGHT, padx=4)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.wait_visibility()
        self.focus_set()

    def _on_ok(self) -> None:
        typ = self.type_var.get().strip()
        producer = self.producer_var.get().strip()
        content = self.content.get("1.0", tk.END).rstrip("\n")
        if not typ:
            messagebox.showwarning("缺少字段", "type 不能为空", parent=self)
            return
        if not producer:
            messagebox.showwarning("缺少字段", "producer 不能为空", parent=self)
            return
        if not content.strip():
            messagebox.showwarning("缺少字段", "content 不能为空", parent=self)
            return

        meta_raw = self.meta.get("1.0", tk.END).strip()
        metadata: dict = {}
        if meta_raw:
            try:
                parsed = json.loads(meta_raw)
            except json.JSONDecodeError as exc:
                messagebox.showerror("metadata 无效", f"JSON 解析失败: {exc}", parent=self)
                return
            if not isinstance(parsed, dict):
                messagebox.showerror("metadata 无效", "metadata 必须是 JSON 对象", parent=self)
                return
            metadata = parsed

        self.result = DataBlock(
            id="",
            type=typ,
            content=content,
            producer=producer,
            metadata=metadata,
        )
        self.destroy()


class ProcessorGui:
    def __init__(self) -> None:
        self.service = ProcessorService(server_client=None)
        self.ui_ids = IdCounter(UI_ID_PREFIX)
        self._blocks: list[DataBlock] = []
        self._busy = False

        self.root = tk.Tk()
        self.root.title("Local_agent — 处理模块测试")
        self.root.geometry("1100x720")
        self.root.minsize(860, 560)

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)

    def _build_ui(self) -> None:
        paned = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left = ttk.Frame(paned, padding=4)
        right = ttk.Frame(paned, padding=4)
        paned.add(left, weight=1)
        paned.add(right, weight=1)

        # —— 输入侧 ——
        ttk.Label(left, text="输入", font=("", 11, "bold")).pack(anchor=tk.W)
        ttk.Label(left, text="总要求").pack(anchor=tk.W, pady=(8, 2))
        self.requirement = scrolledtext.ScrolledText(
            left, height=6, wrap=tk.WORD, font=("Consolas", 10)
        )
        self.requirement.pack(fill=tk.X, expand=False)
        self.requirement.insert(tk.END, "根据上下文写出完整可运行的 Python 代码")

        list_frame = ttk.LabelFrame(left, text="上下文 DataBlock", padding=6)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        list_btns = ttk.Frame(list_frame)
        list_btns.pack(fill=tk.X)
        ttk.Button(list_btns, text="添加…", command=self._on_add).pack(side=tk.LEFT, padx=2)
        ttk.Button(list_btns, text="删除选中", command=self._on_remove).pack(side=tk.LEFT, padx=2)
        ttk.Button(list_btns, text="清空列表", command=self._on_clear_blocks).pack(side=tk.LEFT, padx=2)

        cols = ("id", "type", "producer", "preview")
        self.tree = ttk.Treeview(list_frame, columns=cols, show="headings", height=12)
        self.tree.heading("id", text="id")
        self.tree.heading("type", text="type")
        self.tree.heading("producer", text="producer")
        self.tree.heading("preview", text="content 预览")
        self.tree.column("id", width=70, stretch=False)
        self.tree.column("type", width=80, stretch=False)
        self.tree.column("producer", width=90, stretch=False)
        self.tree.column("preview", width=280)
        self.tree.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        self.tree.bind("<Double-1>", self._on_inspect_block)

        run_row = ttk.Frame(left)
        run_row.pack(fill=tk.X, pady=(8, 0))
        self.run_btn = ttk.Button(run_row, text="处理", command=self._on_process)
        self.run_btn.pack(side=tk.LEFT)
        ttk.Button(run_row, text="预填示例", command=self._load_sample).pack(side=tk.LEFT, padx=6)

        # —— 输出侧 ——
        ttk.Label(right, text="输出", font=("", 11, "bold")).pack(anchor=tk.W)
        self.output = scrolledtext.ScrolledText(
            right, wrap=tk.WORD, font=("Consolas", 10)
        )
        self.output.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(
            fill=tk.X, side=tk.BOTTOM
        )

        self._load_sample()

    def _preview(self, content: str, limit: int = 60) -> str:
        one = content.replace("\n", "\\n")
        return one if len(one) <= limit else one[: limit - 1] + "…"

    def _refresh_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for b in self._blocks:
            self.tree.insert(
                "",
                tk.END,
                iid=b.id,
                values=(b.id, b.type, b.producer, self._preview(b.content)),
            )

    def _on_add(self) -> None:
        dlg = AddBlockDialog(self.root)
        self.root.wait_window(dlg)
        if not dlg.result:
            return
        block = dlg.result
        block.id = self.ui_ids.next()
        self._blocks.append(block)
        self._refresh_tree()
        self.status_var.set(f"已添加 {block.id}")

    def _on_remove(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        ids = set(sel)
        self._blocks = [b for b in self._blocks if b.id not in ids]
        self._refresh_tree()

    def _on_clear_blocks(self) -> None:
        self._blocks.clear()
        self._refresh_tree()

    def _on_inspect_block(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        bid = sel[0]
        block = next((b for b in self._blocks if b.id == bid), None)
        if not block:
            return
        text = json.dumps(block.model_dump(), ensure_ascii=False, indent=2)
        messagebox.showinfo(f"DataBlock {bid}", text, parent=self.root)

    def _load_sample(self) -> None:
        self.requirement.delete("1.0", tk.END)
        self.requirement.insert(tk.END, "根据上下文把代码补全为一个完整的 hello 程序，并加一行注释说明用途")
        self._blocks = [
            DataBlock(
                id=self.ui_ids.next(),
                type="code",
                content="print('hello')",
                producer="ui",
                metadata={"language": "python"},
            )
        ]
        self._refresh_tree()
        self.output.delete("1.0", tk.END)
        self.status_var.set("已载入示例")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.run_btn.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.status_var.set("处理中…" if busy else "就绪")

    def _on_process(self) -> None:
        if self._busy:
            return
        requirement = self.requirement.get("1.0", tk.END).strip()
        if not requirement:
            messagebox.showwarning("缺少要求", "请填写总要求")
            return
        if not self._blocks:
            messagebox.showwarning("缺少数据块", "请至少添加一个 DataBlock")
            return

        req = ProcessRequest(requirement=requirement, blocks=list(self._blocks))
        self._set_busy(True)
        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, "处理中，请稍候…\n")

        def on_done(result) -> None:
            def apply() -> None:
                self._set_busy(False)
                self.output.delete("1.0", tk.END)
                self.output.insert(
                    tk.END,
                    json.dumps(result.model_dump(), ensure_ascii=False, indent=2),
                )
                if result.ok and result.output:
                    self.status_var.set(f"完成 → {result.output.id}")
                else:
                    self.status_var.set(f"失败: {result.error or '未知错误'}")

            self.root.after(0, apply)

        def on_error(tb: str) -> None:
            def apply() -> None:
                self._set_busy(False)
                self.output.delete("1.0", tk.END)
                self.output.insert(tk.END, tb)
                self.status_var.set("异常")

            self.root.after(0, apply)

        run_async(lambda: self.service.process(req, push=False), on_done, on_error)

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    ProcessorGui().run()


if __name__ == "__main__":
    main()
