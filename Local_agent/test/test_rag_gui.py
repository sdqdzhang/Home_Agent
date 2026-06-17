"""
RAG 测试 — tkinter 窗口：入库、问答、向量库浏览与删除。

运行（在 Local_agent 目录下）:
    python test/test_rag_gui.py

依赖:
  - Ollama: nomic-embed-text（嵌入，策略③④入库也需要）
  - 策略② semantic: qwen2.5:3b（LA_RAG_SPLIT_MODEL）
  - 模型总结: 对话模型（如 llama3.2）
  - pip install chromadb
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

_TEST_DIR = Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent
for p in (_ROOT, _TEST_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from common import LogPanel, ROOT, run_async


class RagTestApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("RAG 模块测试")
        self.geometry("1120x920")
        self.minsize(900, 700)
        self._service = None
        self._tree_meta: dict[str, dict] = {}
        self._build()
        self._log(f"项目根目录: {ROOT}")
        self._log("提示: 先入库文档，在「向量库」页刷新查看；支持按文档/片段/整库删除")
        self.after(300, self._refresh_db_tree)

    def _build(self) -> None:
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)

        notebook = ttk.Notebook(frm)
        notebook.pack(fill="both", expand=True)

        tab_ops = ttk.Frame(notebook, padding=4)
        tab_db = ttk.Frame(notebook, padding=4)
        notebook.add(tab_ops, text="入库与问答")
        notebook.add(tab_db, text="向量库")

        self._build_ops_tab(tab_ops)
        self._build_db_tab(tab_db)

    def _build_ops_tab(self, parent: ttk.Frame) -> None:
        srv = ttk.LabelFrame(parent, text="Server Center（可选推送）", padding=6)
        srv.pack(fill="x", pady=4)
        row_srv = ttk.Frame(srv)
        row_srv.pack(fill="x")
        ttk.Label(row_srv, text="地址").pack(side="left")
        self.server_url = tk.StringVar(value="http://127.0.0.1:8765")
        ttk.Entry(row_srv, textvariable=self.server_url, width=50).pack(side="left", padx=4)
        ttk.Button(row_srv, text="测试连接", command=self._on_test_connection).pack(side="left", padx=4)
        self.push_server = tk.BooleanVar(value=False)
        ttk.Checkbutton(srv, text="问答结果推送到 Server Center（Web UI RAG 频道）", variable=self.push_server).pack(
            anchor="w", pady=2
        )

        ingest = ttk.LabelFrame(parent, text="手动入库", padding=6)
        ingest.pack(fill="x", pady=4)

        split_row = ttk.Frame(ingest)
        split_row.pack(fill="x", pady=(0, 4))
        ttk.Label(split_row, text="分块方式").pack(side="left")
        self._split_mode_labels = {
            "rule": "① 规则贪婪合并（快）",
            "semantic": "② 3B 语义裁判（慢）",
            "semantic_embedding": "③ 向量断点（Embedding）",
            "structural": "④ 文档结构（推荐）",
        }
        self.split_mode = tk.StringVar(value="rule")
        self.split_mode_combo = ttk.Combobox(
            split_row,
            values=list(self._split_mode_labels.values()),
            state="readonly",
            width=36,
        )
        self.split_mode_combo.pack(side="left", padx=(6, 0))
        self.split_mode_combo.set(self._split_mode_labels["rule"])
        self.split_mode_combo.bind("<<ComboboxSelected>>", self._on_split_mode_combo)

        row_file = ttk.Frame(ingest)
        row_file.pack(fill="x", pady=2)
        ttk.Label(row_file, text="文件路径").pack(side="left")
        self.file_path = tk.StringVar()
        ttk.Entry(row_file, textvariable=self.file_path, width=58).pack(side="left", padx=4)
        ttk.Button(row_file, text="浏览", command=self._on_browse).pack(side="left")
        ttk.Button(row_file, text="入库文件", command=self._on_ingest_file).pack(side="left", padx=6)

        ttk.Label(ingest, text="或直接粘贴文本入库").pack(anchor="w")
        self.ingest_text = tk.Text(ingest, height=4, font=("Consolas", 10))
        self.ingest_text.pack(fill="x", pady=2)
        ttk.Button(ingest, text="入库文本", command=self._on_ingest_text).pack(anchor="w", pady=2)

        query_frm = ttk.LabelFrame(parent, text="检索问答", padding=6)
        query_frm.pack(fill="x", pady=4)
        row_q = ttk.Frame(query_frm)
        row_q.pack(fill="x", pady=2)
        ttk.Label(row_q, text="问题").pack(side="left")
        self.query = tk.StringVar(value="这份文档讲了什么？")
        ttk.Entry(row_q, textvariable=self.query, width=60).pack(side="left", padx=4)

        row_params = ttk.Frame(query_frm)
        row_params.pack(fill="x", pady=4)
        ttk.Label(row_params, text="top_k").pack(side="left")
        self.top_k = tk.IntVar(value=5)
        ttk.Spinbox(row_params, from_=1, to=20, textvariable=self.top_k, width=5).pack(side="left", padx=4)
        ttk.Label(row_params, text="min_score").pack(side="left", padx=(8, 0))
        self.min_score = tk.DoubleVar(value=0.25)
        ttk.Spinbox(row_params, from_=0.0, to=1.0, increment=0.05, textvariable=self.min_score, width=6).pack(
            side="left", padx=4
        )
        ttk.Label(row_params, text="collection").pack(side="left", padx=(8, 0))
        self.collection_id = tk.StringVar(value="default")
        ttk.Entry(row_params, textvariable=self.collection_id, width=12).pack(side="left", padx=4)
        self.summarize = tk.BooleanVar(value=True)
        ttk.Checkbutton(row_params, text="模型总结（关=直接返回片段）", variable=self.summarize).pack(
            side="left", padx=(12, 0)
        )

        btns = ttk.Frame(parent)
        btns.pack(fill="x", pady=4)
        self.query_btn = ttk.Button(btns, text="提问", command=self._on_query)
        self.query_btn.pack(side="left")
        ttk.Button(btns, text="读取状态", command=self._on_status).pack(side="left", padx=6)
        ttk.Button(btns, text="清空日志", command=self._clear).pack(side="left", padx=6)

        ttk.Label(parent, text="输出").pack(anchor="w")
        self.log = LogPanel(parent)
        self.log.pack(fill="both", expand=True, pady=4)

    def _build_db_tab(self, parent: ttk.Frame) -> None:
        toolbar = ttk.Frame(parent)
        toolbar.pack(fill="x", pady=(0, 4))

        self.db_stats = tk.StringVar(value="尚未加载")
        ttk.Label(toolbar, textvariable=self.db_stats).pack(side="left")

        ttk.Button(toolbar, text="刷新", command=self._refresh_db_tree).pack(side="right", padx=2)
        ttk.Button(toolbar, text="清空 Collection", command=self._on_drop_collection).pack(side="right", padx=2)
        ttk.Button(toolbar, text="删除选中文档", command=self._on_delete_document).pack(side="right", padx=2)
        ttk.Button(toolbar, text="删除选中片段", command=self._on_delete_chunks).pack(side="right", padx=2)

        paned = ttk.PanedWindow(parent, orient="horizontal")
        paned.pack(fill="both", expand=True)

        tree_frame = ttk.Frame(paned)
        paned.add(tree_frame, weight=3)

        cols = ("kind", "name", "id", "extra", "preview")
        self.db_tree = ttk.Treeview(tree_frame, columns=cols, show="tree headings", selectmode="browse")
        self.db_tree.heading("#0", text="结构")
        self.db_tree.column("#0", width=140)
        self.db_tree.heading("kind", text="类型")
        self.db_tree.heading("name", text="名称")
        self.db_tree.heading("id", text="ID")
        self.db_tree.heading("extra", text="块数/索引")
        self.db_tree.heading("preview", text="预览")
        self.db_tree.column("kind", width=56, anchor="center")
        self.db_tree.column("name", width=180)
        self.db_tree.column("id", width=200)
        self.db_tree.column("extra", width=72, anchor="center")
        self.db_tree.column("preview", width=360)

        tree_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.db_tree.yview)
        self.db_tree.configure(yscrollcommand=tree_scroll.set)
        self.db_tree.pack(side="left", fill="both", expand=True)
        tree_scroll.pack(side="right", fill="y")
        self.db_tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        detail_frame = ttk.LabelFrame(paned, text="详情", padding=6)
        paned.add(detail_frame, weight=2)
        self.detail_text = tk.Text(detail_frame, wrap="word", font=("Consolas", 10), state="disabled")
        detail_scroll = ttk.Scrollbar(detail_frame, command=self.detail_text.yview)
        self.detail_text.configure(yscrollcommand=detail_scroll.set)
        self.detail_text.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

    def _service_instance(self):
        if self._service is None:
            from modules.rag.service import RagService

            self._service = RagService(server_client=None)
        return self._service

    def _current_collection(self) -> str:
        return self.collection_id.get().strip() or "default"

    def _on_split_mode_combo(self, _event=None) -> None:
        label = self.split_mode_combo.get()
        for key, text in self._split_mode_labels.items():
            if text == label:
                self.split_mode.set(key)
                return

    def _split_mode_key(self) -> str:
        label = self.split_mode_combo.get()
        for key, text in self._split_mode_labels.items():
            if text == label:
                return key
        return self.split_mode.get() or "rule"

    def _split_ingest_kwargs(self) -> dict:
        mode = self._split_mode_key()
        kwargs: dict = {"split_mode": mode}
        if mode == "semantic":
            kwargs["use_model_split"] = True
        elif mode == "rule":
            kwargs["use_model_split"] = False
        return kwargs

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def _clear(self) -> None:
        self.log.clear()

    def _set_detail(self, text: str) -> None:
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text)
        self.detail_text.configure(state="disabled")

    def _on_browse(self) -> None:
        path = filedialog.askopenfilename(
            title="选择文本文件",
            filetypes=[("文本文件", "*.txt *.md *.json *.py"), ("所有文件", "*.*")],
        )
        if path:
            self.file_path.set(path)

    def _on_test_connection(self) -> None:
        url = self.server_url.get().strip()
        if not url:
            return

        async def _coro():
            from app.config import settings
            from shared.server_center import ServerCenterClient, ensure_client_keys

            private_key, public_key = ensure_client_keys(settings.keys_dir, settings.rsa_key_size)
            client = ServerCenterClient(url, "RAG模块", private_key, public_key, id_prefix="rag")
            health = await client.ping()
            await client.ensure_registered()
            return health

        run_async(
            _coro,
            lambda h: self.after(0, lambda: self._log(f"Server Center 连接成功: {json.dumps(h, ensure_ascii=False)}")),
            lambda e: self.after(0, lambda: self._log(f"连接失败:\n{e}")),
        )

    def _on_ingest_file(self) -> None:
        path = self.file_path.get().strip()
        if not path:
            return
        self._log(f">>> 入库文件: {path} [{self._split_mode_key()}]")

        async def _coro():
            return await self._service_instance().ingest_file(
                path,
                collection_id=self._current_collection(),
                **self._split_ingest_kwargs(),
            )

        run_async(_coro, self._on_ingest_ok, self._on_err)

    def _on_ingest_text(self) -> None:
        text = self.ingest_text.get("1.0", "end").strip()
        if not text:
            return
        self._log(f">>> 入库文本 ({len(text)} 字) [{self._split_mode_key()}]")

        async def _coro():
            return await self._service_instance().ingest_text(
                text,
                collection_id=self._current_collection(),
                **self._split_ingest_kwargs(),
            )

        run_async(_coro, self._on_ingest_ok, self._on_err)

    def _on_ingest_ok(self, result) -> None:
        def show():
            data = result.model_dump() if hasattr(result, "model_dump") else result
            self._log(f"<<< 入库完成: {json.dumps(data, ensure_ascii=False)}")
            self._refresh_db_tree()

        self.after(0, show)

    def _on_query(self) -> None:
        q = self.query.get().strip()
        if not q:
            return
        mode = "模型总结" if self.summarize.get() else "直接返回"
        self.query_btn.configure(state="disabled")
        self._log(f">>> [{mode}] K={self.top_k.get()} min_score={self.min_score.get()} Q: {q}")

        async def _coro():
            if self.push_server.get():
                from app.config import settings
                from modules.rag.service import RagService
                from shared.server_center import ServerCenterClient, ensure_client_keys

                private_key, public_key = ensure_client_keys(settings.keys_dir, settings.rsa_key_size)
                client = ServerCenterClient(
                    self.server_url.get().strip(),
                    "RAG模块",
                    private_key,
                    public_key,
                    id_prefix="rag",
                )
                await client.ensure_registered()
                svc = RagService(server_client=client)
            else:
                svc = self._service_instance()

            return await svc.chat(
                q,
                collection_id=self._current_collection(),
                top_k=self.top_k.get(),
                min_score=self.min_score.get(),
                summarize=self.summarize.get(),
                push=self.push_server.get(),
            )

        run_async(_coro, self._on_query_ok, self._on_err)

    def _on_query_ok(self, result) -> None:
        def show():
            self.query_btn.configure(state="normal")
            data = result.model_dump() if hasattr(result, "model_dump") else result
            rag = data.get("rag", data)
            self._log(f"<<< mode={rag.get('mode')} latency={rag.get('retrieval', {}).get('latency_ms')}ms")
            self._log(f"    answer:\n{rag.get('answer', '')}")
            sources = rag.get("sources") or []
            if sources:
                self._log(f"    sources ({len(sources)}):")
                for s in sources:
                    self._log(f"      - [{s.get('score', 0):.2f}] {s.get('title') or s.get('doc_id')}")

        self.after(0, show)

    def _on_status(self) -> None:
        async def _coro():
            return self._service_instance().status().model_dump()

        run_async(
            _coro,
            lambda d: self.after(0, lambda: self._log(json.dumps(d, ensure_ascii=False, indent=2))),
            self._on_err,
        )

    def _refresh_db_tree(self) -> None:
        coll = self._current_collection()

        async def _coro():
            return self._service_instance().inspect_collection(coll)

        run_async(_coro, lambda d: self.after(0, lambda: self._populate_db_tree(d)), self._on_err)

    def _populate_db_tree(self, data: dict) -> None:
        self.db_tree.delete(*self.db_tree.get_children())
        self._tree_meta.clear()

        coll = data.get("collection_id", self._current_collection())
        chroma_n = data.get("chroma_chunk_count", 0)
        doc_n = data.get("sqlite_document_count", 0)
        sqlite_chunks = data.get("sqlite_chunk_count", 0)
        self.db_stats.set(
            f"Collection: {coll}  |  文档 {doc_n}  |  SQLite 片段 {sqlite_chunks}  |  Chroma 向量 {chroma_n}"
        )

        root_iid = "collection"
        self.db_tree.insert(
            "",
            "end",
            iid=root_iid,
            text=coll,
            values=("集合", coll, coll, f"{doc_n} 文档", f"Chroma {chroma_n} 向量"),
        )
        self._tree_meta[root_iid] = {"type": "collection", "collection_id": coll}

        for doc in data.get("documents") or []:
            doc_id = doc.get("id", "")
            title = doc.get("title") or doc_id
            doc_iid = f"doc:{doc_id}"
            chunks = doc.get("chunks") or []
            self.db_tree.insert(
                root_iid,
                "end",
                iid=doc_iid,
                text=title,
                values=(
                    "文档",
                    title,
                    doc_id,
                    f"{len(chunks)} 块",
                    doc.get("source_ref", "")[:80],
                ),
            )
            self._tree_meta[doc_iid] = {
                "type": "document",
                "collection_id": coll,
                "doc_id": doc_id,
                "doc": doc,
            }

            for chunk in chunks:
                chunk_id = chunk.get("chunk_id", "")
                chunk_iid = f"chunk:{chunk_id}"
                idx = chunk.get("chunk_index")
                idx_label = str(idx + 1) if idx is not None else "?"
                self.db_tree.insert(
                    doc_iid,
                    "end",
                    iid=chunk_iid,
                    text=f"片段 {idx_label}",
                    values=(
                        "片段",
                        title,
                        chunk_id,
                        idx_label,
                        chunk.get("preview", ""),
                    ),
                )
                self._tree_meta[chunk_iid] = {
                    "type": "chunk",
                    "collection_id": coll,
                    "doc_id": doc_id,
                    "chunk_id": chunk_id,
                    "chunk": chunk,
                }

        self.db_tree.item(root_iid, open=True)
        self._set_detail(
            f"Collection: {coll}\n"
            f"文档数: {doc_n}\n"
            f"SQLite 记录片段: {sqlite_chunks}\n"
            f"Chroma 向量数: {chroma_n}\n\n"
            "选中文档或片段可在右侧查看详情；支持删除选中文档、片段或清空整个 collection。"
        )

    def _selected_tree_meta(self) -> dict | None:
        sel = self.db_tree.selection()
        if not sel:
            return None
        return self._tree_meta.get(sel[0])

    def _on_tree_select(self, _event=None) -> None:
        meta = self._selected_tree_meta()
        if not meta:
            return

        if meta["type"] == "collection":
            self._set_detail(
                f"Collection: {meta['collection_id']}\n\n"
                "操作：\n"
                "· 删除选中文档 — 删除该 doc 下全部向量\n"
                "· 删除选中片段 — 按 chunk_id 精准删除\n"
                "· 清空 Collection — 物理删除整个向量集合"
            )
            return

        if meta["type"] == "document":
            doc = meta.get("doc") or {}
            lines = [
                f"文档: {doc.get('title', '')}",
                f"doc_id: {doc.get('id', '')}",
                f"来源: {doc.get('source_type', '')} — {doc.get('source_ref', '')}",
                f"字符数: {doc.get('char_count', 0)}",
                f"分块数: {doc.get('chunk_count', 0)}",
                f"入库时间: {doc.get('created_at', '')}",
                "",
                "下属片段:",
            ]
            for chunk in doc.get("chunks") or []:
                idx = chunk.get("chunk_index")
                label = f"片段 {(idx + 1) if idx is not None else '?'}"
                md = chunk.get("metadata") or {}
                sm = md.get("split_mode", "")
                headers = " > ".join(md[k] for k in sorted(md) if k.startswith("Header_"))
                sm_tag = f" [{sm}]" if sm else ""
                hdr_tag = f" {{ {headers} }}" if headers else ""
                lines.append(f"  · {label}{sm_tag}{hdr_tag}  {chunk.get('chunk_id', '')}")
                lines.append(f"    {chunk.get('preview', '')}")
            self._set_detail("\n".join(lines))
            return

        if meta["type"] == "chunk":
            chunk = meta.get("chunk") or {}
            md = chunk.get("metadata") or {}
            header_lines = [f"{k}: {md[k]}" for k in sorted(md) if k.startswith("Header_")]
            extra = "\n".join(header_lines)
            if md.get("source_ref"):
                extra += f"\nsource_ref: {md['source_ref']}"
            self._set_detail(
                f"chunk_id: {chunk.get('chunk_id', '')}\n"
                f"doc_id: {md.get('doc_id', meta.get('doc_id', ''))}\n"
                f"chunk_index: {chunk.get('chunk_index')}\n"
                f"split_mode: {md.get('split_mode', '')}\n"
                f"{extra}\n"
                f"字符数: {chunk.get('char_count', len(chunk.get('text', '')))}\n"
                f"title: {md.get('title', '')}\n"
                f"url: {md.get('url', '')}\n\n"
                f"--- 原文 ---\n{chunk.get('text', '')}"
            )

    def _on_delete_document(self) -> None:
        meta = self._selected_tree_meta()
        if not meta or meta["type"] not in ("document", "chunk"):
            messagebox.showinfo("提示", "请先在树中选择一个文档或片段（将删除其所属文档）")
            return

        doc_id = meta["doc_id"]
        if not messagebox.askyesno("确认删除", f"删除文档 {doc_id} 及其全部向量？"):
            return

        coll = meta.get("collection_id") or self._current_collection()
        self._log(f">>> 删除文档: {doc_id}")

        async def _coro():
            return self._service_instance().delete_document(doc_id, collection_id=coll).model_dump()

        run_async(_coro, self._on_delete_ok, self._on_err)

    def _on_delete_chunks(self) -> None:
        meta = self._selected_tree_meta()
        if not meta or meta["type"] != "chunk":
            messagebox.showinfo("提示", "请先选择一个「片段」节点")
            return

        chunk_id = meta["chunk_id"]
        coll = meta.get("collection_id") or self._current_collection()
        if not messagebox.askyesno("确认删除", f"删除片段 {chunk_id} ？"):
            return

        self._log(f">>> 删除片段: {chunk_id}")

        async def _coro():
            return self._service_instance().delete_chunks([chunk_id], collection_id=coll).model_dump()

        run_async(_coro, self._on_delete_ok, self._on_err)

    def _on_drop_collection(self) -> None:
        coll = self._current_collection()
        if not messagebox.askyesno(
            "确认清空",
            f"将物理删除 collection「{coll}」的全部向量与 SQLite 元数据，不可恢复。\n\n确定继续？",
        ):
            return

        self._log(f">>> 清空 collection: {coll}")

        async def _coro():
            return self._service_instance().drop_collection(coll).model_dump()

        run_async(_coro, self._on_delete_ok, self._on_err)

    def _on_delete_ok(self, result: dict) -> None:
        def show():
            self._log(f"<<< 删除完成: {json.dumps(result, ensure_ascii=False)}")
            self._refresh_db_tree()

        self.after(0, show)

    def _on_err(self, err: str) -> None:
        self.after(0, lambda: (self.query_btn.configure(state="normal"), self._log(f"!!! 错误:\n{err}")))


if __name__ == "__main__":
    app = RagTestApp()
    app.mainloop()
