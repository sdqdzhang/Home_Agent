"""
记忆模块测试 — tkinter：observe / ingest-dialogue / recall / reflect / 向量库浏览。

运行（在 Local_agent 目录下）:
    python test/test_memory_gui.py
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

SAMPLE_DIALOGUE = """用户: 帮我写一个爬 example.com 的 Python 脚本
助手: 好的，我先用 httpx 同步请求试试
[工具] 网页爬取模块: crawl example.com → 成功，提取正文 1200 字
用户: 报错说连接超时，能不能改成异步并发？
助手: 改用 asyncio + aiohttp，并调大超时
[工具] 网页爬取模块: 第二次爬取成功，耗时 3.2s
用户: 可以，以后爬虫都用这套异步方案"""

from common import LogPanel, ROOT, run_async


class MemoryTestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("记忆模块测试")
        self.geometry("1040x880")
        self.minsize(900, 720)
        self._service = None
        self._tree_meta: dict[str, dict] = {}
        self._build()
        self._log(f"项目根目录: {ROOT}")
        self.after(300, self._refresh_archive_tree)

    def _get_service(self):
        if self._service is None:
            from modules.memory.service import MemoryService

            self._service = MemoryService(server_client=None)
        return self._service

    def _build(self) -> None:
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)

        notebook = ttk.Notebook(frm)
        notebook.pack(fill="both", expand=True)

        tab_ops = ttk.Frame(notebook, padding=4)
        tab_db = ttk.Frame(notebook, padding=4)
        notebook.add(tab_ops, text="操作")
        notebook.add(tab_db, text="向量库")

        self._build_ops_tab(tab_ops)
        self._build_db_tab(tab_db)

    def _build_ops_tab(self, parent: ttk.Frame) -> None:
        status_frm = ttk.LabelFrame(parent, text="状态", padding=6)
        status_frm.pack(fill="x", pady=4)
        row = ttk.Frame(status_frm)
        row.pack(fill="x")
        ttk.Button(row, text="刷新状态", command=self._on_status).pack(side="left")
        self.status_var = tk.StringVar(value="（未加载）")
        ttk.Label(row, textvariable=self.status_var).pack(side="left", padx=8)

        observe_frm = ttk.LabelFrame(parent, text="Observe", padding=6)
        observe_frm.pack(fill="x", pady=4)
        self.observe_text = tk.Text(observe_frm, height=3, wrap="word")
        self.observe_text.pack(fill="x", pady=2)
        self.observe_text.insert("1.0", "用户今天询问了 Python 异步爬虫的实现方式")
        btn_row = ttk.Frame(observe_frm)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="写入 Observe", command=self._on_observe).pack(side="left")

        dialogue_frm = ttk.LabelFrame(parent, text="Ingest Dialogue（summarize → tag → assess → 入库）", padding=6)
        dialogue_frm.pack(fill="x", pady=4)
        self.dialogue_text = tk.Text(dialogue_frm, height=7, wrap="word")
        self.dialogue_text.pack(fill="x", pady=2)
        self.dialogue_text.insert("1.0", SAMPLE_DIALOGUE)
        drow = ttk.Frame(dialogue_frm)
        drow.pack(fill="x")
        ttk.Button(drow, text="总结并入库", command=self._on_ingest_dialogue).pack(side="left")
        ttk.Button(drow, text="载入示例", command=self._fill_sample_dialogue).pack(side="left", padx=4)

        recall_frm = ttk.LabelFrame(parent, text="Recall / Context / Reflect", padding=6)
        recall_frm.pack(fill="x", pady=4)
        rq = ttk.Frame(recall_frm)
        rq.pack(fill="x")
        ttk.Label(rq, text="查询").pack(side="left")
        self.recall_query = tk.StringVar(value="Python 爬虫")
        ttk.Entry(rq, textvariable=self.recall_query, width=40).pack(side="left", padx=4)
        ttk.Button(rq, text="检索", command=self._on_recall).pack(side="left", padx=2)
        ttk.Button(rq, text="Context", command=self._on_context).pack(side="left", padx=2)
        ttk.Label(rq, text="reflect limit").pack(side="left", padx=(8, 0))
        self.reflect_limit = tk.IntVar(value=10)
        ttk.Spinbox(rq, from_=1, to=20, textvariable=self.reflect_limit, width=4).pack(side="left", padx=2)
        ttk.Button(rq, text="Reflect", command=self._on_reflect).pack(side="left", padx=2)

        core_frm = ttk.LabelFrame(parent, text="Core Memory", padding=6)
        core_frm.pack(fill="x", pady=4)
        cr = ttk.Frame(core_frm)
        cr.pack(fill="x")
        ttk.Label(cr, text="key").pack(side="left")
        self.core_key = tk.StringVar(value="user_theme")
        ttk.Entry(cr, textvariable=self.core_key, width=14).pack(side="left", padx=4)
        ttk.Label(cr, text="value").pack(side="left")
        self.core_value = tk.StringVar(value="深色主题")
        ttk.Entry(cr, textvariable=self.core_value, width=24).pack(side="left", padx=4)
        ttk.Button(cr, text="写入", command=self._on_core_upsert).pack(side="left", padx=2)
        ttk.Button(cr, text="列出", command=self._on_core_list).pack(side="left")

        log_frm = ttk.LabelFrame(parent, text="输出", padding=6)
        log_frm.pack(fill="both", expand=True, pady=4)
        self.log = LogPanel(log_frm)
        self.log.pack(fill="both", expand=True)

    def _build_db_tab(self, parent: ttk.Frame) -> None:
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", pady=(0, 4))
        ttk.Button(toolbar, text="刷新", command=self._refresh_archive_tree).pack(side="left")
        ttk.Button(toolbar, text="清空全部数据", command=self._on_clear_all).pack(side="left", padx=6)
        self.db_stats = tk.StringVar(value="")
        ttk.Label(toolbar, textvariable=self.db_stats).pack(side="left", padx=8)

        body = ttk.Panedwindow(parent, orient="horizontal")
        body.pack(fill="both", expand=True)

        tree_frm = ttk.Frame(body)
        detail_frm = ttk.LabelFrame(body, text="详情", padding=6)
        body.add(tree_frm, weight=2)
        body.add(detail_frm, weight=3)

        cols = ("type", "kind", "importance", "tags", "preview")
        self.db_tree = ttk.Treeview(tree_frm, columns=cols, show="tree headings", height=22)
        self.db_tree.heading("#0", text="节点")
        self.db_tree.heading("type", text="类型")
        self.db_tree.heading("kind", text="kind")
        self.db_tree.heading("importance", text="分数")
        self.db_tree.heading("tags", text="tags")
        self.db_tree.heading("preview", text="摘要")
        self.db_tree.column("#0", width=180)
        self.db_tree.column("type", width=60)
        self.db_tree.column("kind", width=80)
        self.db_tree.column("importance", width=45)
        self.db_tree.column("tags", width=180)
        self.db_tree.column("preview", width=220)
        scroll = ttk.Scrollbar(tree_frm, orient="vertical", command=self.db_tree.yview)
        self.db_tree.configure(yscrollcommand=scroll.set)
        self.db_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.db_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        self.detail_text = tk.Text(detail_frm, wrap="word", font=("Consolas", 10))
        self.detail_text.pack(fill="both", expand=True)
        self.detail_text.configure(state="disabled")

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def _set_detail(self, text: str) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text)
        self.detail_text.configure(state="disabled")

    def _fill_sample_dialogue(self) -> None:
        self.dialogue_text.delete("1.0", "end")
        self.dialogue_text.insert("1.0", SAMPLE_DIALOGUE)

    def _tags_preview(self, tags: list[str] | None) -> str:
        if not tags:
            return ""
        return ", ".join(tags[:6])

    def _refresh_archive_tree(self) -> None:
        data = self._get_service().inspect_archive()
        self._populate_db_tree(data)

    def _populate_db_tree(self, data: dict) -> None:
        self.db_tree.delete(*self.db_tree.get_children())
        self._tree_meta.clear()

        coll = data.get("collection", "archive")
        chroma_n = data.get("chroma_count", 0)
        mem_n = data.get("memory_count", 0)
        self.db_stats.set(
            f"Chroma: {data.get('chroma_dir', '')} | 向量 {chroma_n} | memory_id {mem_n} | "
            f"工作记忆 {data.get('working_count', 0)} | Core {data.get('core_count', 0)}"
        )

        root_iid = "archive_root"
        self.db_tree.insert(
            "",
            "end",
            iid=root_iid,
            text=f"archive ({chroma_n})",
            values=("collection", "", "", "", coll),
        )
        self._tree_meta[root_iid] = {"type": "collection", "data": data}

        grouped = data.get("grouped") or {}
        for memory_id in sorted(grouped.keys(), key=lambda k: grouped[k][0].get("created_at", ""), reverse=True):
            chunks = grouped[memory_id]
            first = chunks[0]
            tags = first.get("tags") or []
            preview = (first.get("text") or "")[:50]
            if len(first.get("text") or "") > 50:
                preview += "…"
            mid_iid = f"mem_{memory_id}"
            self.db_tree.insert(
                root_iid,
                "end",
                iid=mid_iid,
                text=memory_id,
                values=(
                    "memory",
                    first.get("kind", ""),
                    f"{first.get('importance', 0):.1f}",
                    self._tags_preview(tags),
                    preview,
                ),
            )
            self._tree_meta[mid_iid] = {"type": "memory", "memory_id": memory_id, "chunks": chunks}

            for chunk in chunks:
                cid = chunk.get("chunk_id", "")
                chunk_iid = f"chunk_{cid}"
                if self.db_tree.exists(chunk_iid):
                    chunk_iid = f"chunk_{cid}_{memory_id}"
                ctags = chunk.get("tags") or []
                cpreview = (chunk.get("text") or "")[:40]
                self.db_tree.insert(
                    mid_iid,
                    "end",
                    iid=chunk_iid,
                    text=cid,
                    values=(
                        "vector",
                        chunk.get("kind", ""),
                        f"{chunk.get('importance', 0):.1f}",
                        self._tags_preview(ctags),
                        cpreview,
                    ),
                )
                self._tree_meta[chunk_iid] = {"type": "chunk", "chunk": chunk}

        work_root = "working_root"
        working_items = self._get_service().working.list_all()
        self.db_tree.insert(
            "",
            "end",
            iid=work_root,
            text=f"工作记忆 SQLite ({len(working_items)})",
            values=("working", "", "", "", "未入 Chroma 的条目"),
        )
        self._tree_meta[work_root] = {"type": "working_root", "items": working_items}
        for item in working_items:
            wid = item["id"]
            wiid = f"work_{wid}"
            tags = (item.get("metadata") or {}).get("tags") or []
            preview = (item.get("content") or "")[:50]
            self.db_tree.insert(
                work_root,
                "end",
                iid=wiid,
                text=wid,
                values=(
                    "working",
                    item.get("kind", ""),
                    f"{item.get('importance', 0):.1f}",
                    self._tags_preview(tags),
                    preview,
                ),
            )
            self._tree_meta[wiid] = {"type": "working", "item": item}

    def _on_tree_select(self, _event=None) -> None:
        sel = self.db_tree.selection()
        if not sel:
            return
        meta = self._tree_meta.get(sel[0])
        if not meta:
            return
        kind = meta.get("type")
        if kind == "chunk":
            self._set_detail(json.dumps(meta["chunk"], ensure_ascii=False, indent=2))
        elif kind == "memory":
            self._set_detail(json.dumps(meta["chunks"], ensure_ascii=False, indent=2))
        elif kind == "working":
            self._set_detail(json.dumps(meta["item"], ensure_ascii=False, indent=2))
        elif kind == "collection":
            self._set_detail(json.dumps(meta["data"], ensure_ascii=False, indent=2))
        elif kind == "working_root":
            self._set_detail(json.dumps(meta["items"], ensure_ascii=False, indent=2))

    def _on_clear_all(self) -> None:
        if not messagebox.askyesno(
            "确认清空",
            "将删除：\n· Chroma 向量库 (data/memory/chroma)\n· 工作记忆 SQLite 表\n· Core Memory\n\n此操作不可恢复，继续？",
        ):
            return
        result = self._get_service().clear_all_data(include_core=True)
        self._log("=== 清空全部数据 ===")
        self._log(json.dumps(result, ensure_ascii=False, indent=2))
        self._on_status()
        self._refresh_archive_tree()
        messagebox.showinfo("完成", f"已清空：向量 {result['chroma_removed']}，工作记忆 {result['working_removed']}，Core {result['core_removed']}")

    def _on_status(self) -> None:
        st = self._get_service().status()
        self.status_var.set(
            f"工作记忆 {st.working_count}/{st.working_max_size} · "
            f"Archive {st.archive_count} · Core {st.core_count}"
        )
        self._log(json.dumps(st.model_dump(), ensure_ascii=False, indent=2))

    def _on_ingest_dialogue(self) -> None:
        dialogue = self.dialogue_text.get("1.0", "end").strip()
        if not dialogue:
            messagebox.showwarning("提示", "请输入对话原文")
            return

        run_async(
            lambda: self._get_service().ingest_dialogue({"dialogue": dialogue}),
            self._on_ingest_dialogue_done,
            self._on_error,
        )

    def _on_ingest_dialogue_done(self, result) -> None:
        self._log("=== Ingest Dialogue ===")
        self._log(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        self._on_status()
        self._refresh_archive_tree()

    def _on_observe(self) -> None:
        content = self.observe_text.get("1.0", "end").strip()
        if not content:
            return
        run_async(
            lambda: self._get_service().observe({"content": content}),
            self._on_observe_done,
            self._on_error,
        )

    def _on_observe_done(self, result) -> None:
        self._log("=== Observe ===")
        self._log(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        self._on_status()
        self._refresh_archive_tree()

    def _on_recall(self) -> None:
        query = self.recall_query.get().strip()
        if not query:
            return
        run_async(
            lambda: self._get_service().recall({"query": query}),
            self._on_recall_done,
            self._on_error,
        )

    def _on_recall_done(self, result) -> None:
        self._log("=== Recall（含 tag_score / vector_relevance_score）===")
        self._log(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))

    def _on_context(self) -> None:
        ctx = self._get_service().get_context()
        self._log("=== Context ===")
        self._log(json.dumps(ctx, ensure_ascii=False, indent=2))

    def _on_reflect(self) -> None:
        limit = int(self.reflect_limit.get())
        run_async(
            lambda: self._get_service().reflect({"limit": limit}),
            self._on_reflect_done,
            self._on_error,
        )

    def _on_reflect_done(self, result) -> None:
        self._log("=== Reflect ===")
        self._log(json.dumps(result.model_dump(), ensure_ascii=False, indent=2))
        if not result.success:
            messagebox.showwarning("反思未写入", result.reason or "失败")
        self._on_status()
        self._refresh_archive_tree()

    def _on_core_upsert(self) -> None:
        row = self._get_service().upsert_core(
            {"key": self.core_key.get().strip(), "value": self.core_value.get().strip()}
        )
        self._log("=== Core upsert ===")
        self._log(json.dumps(row.model_dump(), ensure_ascii=False, indent=2))
        self._on_status()
        self._refresh_archive_tree()

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
