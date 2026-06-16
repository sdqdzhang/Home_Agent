"""
RAG 测试 — tkinter 窗口：手动入库、检索问答、可选模型总结。

运行（在 Local_agent 目录下）:
    python test/test_rag_gui.py

依赖:
  - Ollama 已拉取 nomic-embed-text（嵌入）与对话模型（如 llama3.2，仅在「模型总结」时需要）
  - pip install chromadb
"""

from __future__ import annotations

import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

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
        self.geometry("960x780")
        self._service = None
        self._server_client = None
        self._build()
        self._log(f"项目根目录: {ROOT}")
        self._log("提示: 先入库文档，再提问；勾选「模型总结」需 Ollama 对话模型")

    def _build(self) -> None:
        frm = ttk.Frame(self, padding=8)
        frm.pack(fill="both", expand=True)

        srv = ttk.LabelFrame(frm, text="Server Center（可选推送）", padding=6)
        srv.pack(fill="x", pady=4)
        row_srv = ttk.Frame(srv)
        row_srv.pack(fill="x")
        ttk.Label(row_srv, text="地址").pack(side="left")
        self.server_url = tk.StringVar(value="http://127.0.0.1:8765")
        ttk.Entry(row_srv, textvariable=self.server_url, width=50).pack(side="left", padx=4)
        ttk.Button(row_srv, text="测试连接", command=self._on_test_connection).pack(side="left", padx=4)
        self.push_server = tk.BooleanVar(value=False)
        ttk.Checkbutton(srv, text="问答结果推送到 Server Center（Web UI RAG 频道）", variable=self.push_server).pack(anchor="w", pady=2)

        ingest = ttk.LabelFrame(frm, text="手动入库", padding=6)
        ingest.pack(fill="x", pady=4)
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

        query_frm = ttk.LabelFrame(frm, text="检索问答", padding=6)
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
        ttk.Spinbox(row_params, from_=0.0, to=1.0, increment=0.05, textvariable=self.min_score, width=6).pack(side="left", padx=4)
        ttk.Label(row_params, text="collection").pack(side="left", padx=(8, 0))
        self.collection_id = tk.StringVar(value="default")
        ttk.Entry(row_params, textvariable=self.collection_id, width=12).pack(side="left", padx=4)
        self.summarize = tk.BooleanVar(value=True)
        ttk.Checkbutton(row_params, text="模型总结（关=直接返回片段）", variable=self.summarize).pack(side="left", padx=(12, 0))

        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=4)
        self.query_btn = ttk.Button(btns, text="提问", command=self._on_query)
        self.query_btn.pack(side="left")
        ttk.Button(btns, text="读取状态", command=self._on_status).pack(side="left", padx=6)
        ttk.Button(btns, text="清空日志", command=self._clear).pack(side="left", padx=6)

        ttk.Label(frm, text="输出").pack(anchor="w")
        self.log = LogPanel(frm)
        self.log.pack(fill="both", expand=True, pady=4)

    def _service_instance(self):
        if self._service is None:
            from modules.rag.service import RagService

            self._service = RagService(server_client=self._server_client)
        return self._service

    def _log(self, msg: str) -> None:
        self.log.append(msg)

    def _clear(self) -> None:
        self.log.clear()

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
            from shared.server_center import ServerCenterClient, ensure_client_keys
            from app.config import settings

            private_key, public_key = ensure_client_keys(settings.keys_dir, settings.rsa_key_size)
            client = ServerCenterClient(url, "RAG模块", private_key, public_key, id_prefix="rag")
            health = await client.ping()
            await client.ensure_registered()
            return health

        def ok(health):
            self.after(0, lambda: self._log(f"Server Center 连接成功: {json.dumps(health, ensure_ascii=False)}"))

        def err(msg):
            self.after(0, lambda: self._log(f"连接失败:\n{msg}"))

        run_async(_coro, ok, err)

    def _on_ingest_file(self) -> None:
        path = self.file_path.get().strip()
        if not path:
            return
        self._log(f">>> 入库文件: {path}")

        async def _coro():
            svc = self._service_instance()
            return await svc.ingest_file(path, collection_id=self.collection_id.get().strip() or None)

        run_async(_coro, self._on_ingest_ok, self._on_err)

    def _on_ingest_text(self) -> None:
        text = self.ingest_text.get("1.0", "end").strip()
        if not text:
            return
        self._log(f">>> 入库文本 ({len(text)} 字)")

        async def _coro():
            svc = self._service_instance()
            return await svc.ingest_text(text, collection_id=self.collection_id.get().strip() or None)

        run_async(_coro, self._on_ingest_ok, self._on_err)

    def _on_ingest_ok(self, result) -> None:
        def show():
            data = result.model_dump() if hasattr(result, "model_dump") else result
            self._log(f"<<< 入库完成: {json.dumps(data, ensure_ascii=False)}")

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
                from shared.server_center import ensure_client_keys
                from app.config import settings

                private_key, public_key = ensure_client_keys(settings.keys_dir, settings.rsa_key_size)
                from shared.server_center import ServerCenterClient

                client = ServerCenterClient(
                    self.server_url.get().strip(),
                    "RAG模块",
                    private_key,
                    public_key,
                    id_prefix="rag",
                )
                await client.ensure_registered()
                from modules.rag.service import RagService

                svc = RagService(server_client=client)
            else:
                svc = self._service_instance()

            return await svc.chat(
                q,
                collection_id=self.collection_id.get().strip() or None,
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

        run_async(_coro, lambda d: self.after(0, lambda: self._log(json.dumps(d, ensure_ascii=False, indent=2))), self._on_err)

    def _on_err(self, err: str) -> None:
        self.after(0, lambda: (self.query_btn.configure(state="normal"), self._log(f"!!! 错误:\n{err}")))


if __name__ == "__main__":
    app = RagTestApp()
    app.mainloop()
