"""
各模块固定日志与记录 — tkinter 查看与清理工具。

运行（在 Local_agent 目录下）:
    python test/test_storage_gui.py

覆盖:
  - SQLite: llm / crawler / executor / rag / memory / security / messages
  - 日志: crawler/logs, executor/logs
  - 产物: crawler/artifacts
  - 向量: rag/chroma, memory/chroma
  - 图片: env/screenshots, env/camera
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

_TEST_DIR = Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent
for p in (_ROOT, _TEST_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common import LogPanel
from storage_registry import (
    StorageFile,
    StorageGroup,
    clear_group_files,
    delete_storage_item,
    format_mtime,
    format_size,
    read_text_preview,
    scan_all,
)


class StorageGuiApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("HomeAgent 日志与记录清理")
        self.geometry("1180x760")
        self.minsize(960, 620)

        self._groups: list[StorageGroup] = []
        self._items: list[StorageFile] = []
        self._item_by_iid: dict[str, StorageFile] = {}
        self._group_by_iid: dict[str, StorageGroup] = {}

        self._build()
        self._log("扫描各模块 data/ 下的数据库、日志与记录…")
        self._log("提示: 清理前建议停止 Local Agent / Server Center，避免运行中写入冲突")
        self.refresh()

    def _build(self) -> None:
        root = ttk.Frame(self, padding=8)
        root.pack(fill="both", expand=True)

        toolbar = ttk.Frame(root)
        toolbar.pack(fill="x", pady=(0, 6))
        ttk.Button(toolbar, text="刷新", command=self.refresh).pack(side="left")
        ttk.Button(toolbar, text="删除选中", command=self._delete_selected).pack(side="left", padx=6)
        ttk.Button(toolbar, text="清空当前分类", command=self._clear_current_group).pack(side="left")
        ttk.Button(toolbar, text="在资源管理器中打开", command=self._open_in_explorer).pack(side="left", padx=6)

        self.summary_var = tk.StringVar(value="")
        ttk.Label(root, textvariable=self.summary_var, foreground="#555").pack(anchor="w", pady=(0, 4))

        paned = ttk.Panedwindow(root, orient="horizontal")
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, padding=4)
        paned.add(left, weight=2)

        tree_frm = ttk.Frame(left)
        tree_frm.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(
            tree_frm,
            columns=("size", "mtime", "detail"),
            show="tree headings",
            selectmode="extended",
        )
        self.tree.heading("#0", text="模块 / 文件")
        self.tree.heading("size", text="大小")
        self.tree.heading("mtime", text="修改时间")
        self.tree.heading("detail", text="说明")
        self.tree.column("#0", width=320, minwidth=200)
        self.tree.column("size", width=80, anchor="e")
        self.tree.column("mtime", width=140)
        self.tree.column("detail", width=280)
        scroll = ttk.Scrollbar(tree_frm, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        right = ttk.Frame(paned, padding=4)
        paned.add(right, weight=3)

        meta = ttk.LabelFrame(right, text="选中项", padding=6)
        meta.pack(fill="x", pady=(0, 6))
        self.meta_text = tk.Text(meta, height=5, font=("Consolas", 10), wrap="word")
        self.meta_text.pack(fill="x")

        preview_frm = ttk.LabelFrame(right, text="内容预览", padding=6)
        preview_frm.pack(fill="both", expand=True)
        self.preview = tk.Text(preview_frm, wrap="none", font=("Consolas", 10))
        px = ttk.Scrollbar(preview_frm, orient="horizontal", command=self.preview.xview)
        py = ttk.Scrollbar(preview_frm, orient="vertical", command=self.preview.yview)
        self.preview.configure(xscrollcommand=px.set, yscrollcommand=py.set)
        self.preview.grid(row=0, column=0, sticky="nsew")
        py.grid(row=0, column=1, sticky="ns")
        px.grid(row=1, column=0, sticky="ew")
        preview_frm.rowconfigure(0, weight=1)
        preview_frm.columnconfigure(0, weight=1)

        self.log = LogPanel(root)
        self.log.pack(fill="both", expand=False, pady=(6, 0))

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self._item_by_iid.clear()
        self._group_by_iid.clear()
        self.preview.delete("1.0", tk.END)
        self.meta_text.delete("1.0", tk.END)

        try:
            self._groups, self._items = scan_all()
        except Exception as exc:
            messagebox.showerror("扫描失败", str(exc))
            self._log(f"扫描失败: {exc}")
            return

        module_nodes: dict[str, str] = {}
        group_nodes: dict[tuple[str, str], str] = {}
        total_bytes = 0
        file_count = 0

        for group in self._groups:
            mod_iid = module_nodes.get(group.module)
            if not mod_iid:
                mod_iid = self.tree.insert("", "end", text=group.module, open=True)
                module_nodes[group.module] = mod_iid

            grp_key = (group.module, group.category)
            grp_iid = group_nodes.get(grp_key)
            if not grp_iid:
                grp_iid = self.tree.insert(
                    mod_iid,
                    "end",
                    text=group.category,
                    values=("", "", group.description),
                    open=True,
                )
                group_nodes[grp_key] = grp_iid
                self._group_by_iid[grp_iid] = group

            group_items = [it for it in self._items if it.group == group]
            for item in group_items:
                if item.detail in ("文件不存在", "目录不存在"):
                    self.tree.insert(
                        grp_iid,
                        "end",
                        text=item.path.name if item.path.name else str(item.path),
                        values=("—", "—", item.detail),
                    )
                    continue
                if item.detail == "（空目录）" and item.path.is_dir():
                    self.tree.insert(grp_iid, "end", text="（空）", values=("—", "—", item.detail))
                    continue

                label = item.path.name if item.path.is_file() else f"[目录] {item.path.name}"
                iid = self.tree.insert(
                    grp_iid,
                    "end",
                    text=label,
                    values=(
                        format_size(item.size_bytes),
                        format_mtime(item.mtime),
                        item.detail,
                    ),
                )
                self._item_by_iid[iid] = item
                total_bytes += item.size_bytes
                file_count += 1

        self.summary_var.set(
            f"共 {len(self._groups)} 个存储分类，{file_count} 个可清理项，合计约 {format_size(total_bytes)}"
        )
        self._log(f"刷新完成: {file_count} 项，{format_size(total_bytes)}")

    def _selected_items(self) -> list[StorageFile]:
        items: list[StorageFile] = []
        for iid in self.tree.selection():
            if iid in self._item_by_iid:
                items.append(self._item_by_iid[iid])
        return items

    def _current_group(self) -> StorageGroup | None:
        sel = self.tree.selection()
        if not sel:
            return None
        iid = sel[0]
        if iid in self._group_by_iid:
            return self._group_by_iid[iid]
        parent = self.tree.parent(iid)
        if parent in self._group_by_iid:
            return self._group_by_iid[parent]
        return None

    def _on_select(self, _event=None) -> None:
        items = self._selected_items()
        self.meta_text.delete("1.0", tk.END)
        self.preview.delete("1.0", tk.END)
        if not items:
            grp = self._current_group()
            if grp:
                self.meta_text.insert(
                    tk.END,
                    f"分类: {grp.module} / {grp.category}\n"
                    f"路径: {grp.path}\n"
                    f"类型: {grp.kind}\n"
                    f"说明: {grp.description}",
                )
            return
        if len(items) == 1:
            item = items[0]
            self.meta_text.insert(
                tk.END,
                f"模块: {item.group.module}\n"
                f"分类: {item.group.category}\n"
                f"路径: {item.path}\n"
                f"大小: {format_size(item.size_bytes)}\n"
                f"修改: {format_mtime(item.mtime)}\n"
                f"说明: {item.detail or item.group.description}",
            )
            if item.path.is_file() and item.path.suffix.lower() in (".log", ".json", ".db", ".txt"):
                self.preview.insert(tk.END, read_text_preview(item.path))
            elif item.group.kind == "chroma_dir":
                self.preview.insert(tk.END, f"Chroma 目录\n{item.path}\n\n{item.detail}")
            else:
                self.preview.insert(tk.END, f"（无可预览文本内容）\n{item.path}")
        else:
            lines = [f"- {it.path} ({format_size(it.size_bytes)})" for it in items]
            self.meta_text.insert(tk.END, f"已选 {len(items)} 项:\n" + "\n".join(lines))

    def _confirm_delete(self, title: str, body: str) -> bool:
        return messagebox.askyesno(title, body + "\n\n此操作不可恢复，是否继续？")

    def _delete_selected(self) -> None:
        items = self._selected_items()
        if not items:
            messagebox.showinfo("提示", "请在树中选中具体文件或目录项（不是模块名）")
            return
        names = "\n".join(f"• {it.path}" for it in items[:12])
        if len(items) > 12:
            names += f"\n…等共 {len(items)} 项"
        if not self._confirm_delete("删除选中", f"将删除以下项:\n{names}"):
            return
        for item in items:
            try:
                msg = delete_storage_item(item)
                self._log(msg)
            except Exception as exc:
                self._log(f"失败 {item.path}: {exc}")
        self.refresh()

    def _clear_current_group(self) -> None:
        grp = self._current_group()
        if not grp:
            messagebox.showinfo("提示", "请先选中一个分类节点（如「任务日志」）")
            return
        if not self._confirm_delete(
            "清空分类",
            f"将清理 [{grp.module}] {grp.category}\n路径: {grp.path}\n{grp.description}",
        ):
            return
        try:
            for msg in clear_group_files(grp):
                self._log(msg)
        except Exception as exc:
            messagebox.showerror("清理失败", str(exc))
            self._log(f"清理失败: {exc}")
        self.refresh()

    def _open_in_explorer(self) -> None:
        items = self._selected_items()
        path: Path | None = None
        if items:
            path = items[0].path
        else:
            grp = self._current_group()
            if grp:
                path = grp.path
        if not path:
            messagebox.showinfo("提示", "请先选中一项")
            return
        target = path if path.is_dir() else path.parent
        if not target.exists():
            messagebox.showwarning("路径不存在", str(target))
            return
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(target)], check=False)
        else:
            subprocess.run(["xdg-open", str(target)], check=False)


def main() -> None:
    app = StorageGuiApp()
    app.mainloop()


if __name__ == "__main__":
    main()
