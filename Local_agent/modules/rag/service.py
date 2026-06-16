from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from shared.server_center.client import ServerCenterClient
from modules.rag import DEFAULT_MSG_TYPE, MODULE_ALIASES
from modules.rag.chat.memory import ConversationMemory
from modules.rag.config import rag_settings
from modules.rag.index.chroma_store import ChromaStore
from modules.rag.ingest.chunker import chunk_text
from modules.rag.ingest.loader import load_file_text
from modules.rag.model.assistant import RagAssistant
from modules.rag.retrieval.retriever import RagRetriever
from modules.rag.schemas import (
    RagChatResponse,
    RagCollectionInfo,
    RagIngestResponse,
    RagQueryRequest,
    RagQueryResponse,
    RagStatusResponse,
    RetrievalMeta,
)
from modules.rag.storage import DocumentStore

logger = logging.getLogger(__name__)


class RagService:
    """RAG 服务：手动入库、检索问答、可选模型总结、Server Center 对接。"""

    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        rag_settings.data_dir.mkdir(parents=True, exist_ok=True)
        rag_settings.documents_dir.mkdir(parents=True, exist_ok=True)

        self.server = server_client
        self.store = ChromaStore()
        self.meta = DocumentStore(rag_settings.db_path)
        self.retriever = RagRetriever(self.store)
        self.assistant = RagAssistant()
        self.memory = ConversationMemory(rag_settings.db_path)

    async def handle_incoming_message(self, data: dict[str, Any]) -> None:
        if data.get("name") != "user_ui":
            return
        target = data.get("target", "")
        if target not in MODULE_ALIASES:
            return

        msg_type = data.get("msg_type", "text")
        message = data.get("message") or {}

        if msg_type != "text":
            return

        payload = message.get("payload") or {}
        action = payload.get("action")

        if action == "ingest_file":
            path = payload.get("path") or message.get("text", "")
            await self.ingest_file(path, collection_id=payload.get("collection_id"), title=payload.get("title", ""))
            return

        if action == "ingest_text":
            text = payload.get("text") or message.get("text", "")
            await self.ingest_text(
                text,
                collection_id=payload.get("collection_id"),
                title=payload.get("title", "inline_text"),
                source_ref=payload.get("source_ref", ""),
            )
            return

        text = message.get("text", "").strip()
        if not text:
            return

        session_id = message.get("session_id") or "default"
        await self.chat(
            text,
            session_id=session_id,
            collection_id=payload.get("collection_id"),
            top_k=payload.get("top_k"),
            min_score=payload.get("min_score"),
            summarize=payload.get("summarize"),
            push=True,
        )

    async def ingest_file(
        self,
        path: str,
        *,
        collection_id: str | None = None,
        title: str = "",
    ) -> RagIngestResponse:
        collection = collection_id or rag_settings.default_collection
        content, detected_title = load_file_text(path)
        final_title = title or detected_title
        return await self._ingest_content(
            content,
            collection_id=collection,
            title=final_title,
            source_type="file",
            source_ref=str(Path(path).expanduser().resolve()),
        )

    async def ingest_text(
        self,
        text: str,
        *,
        collection_id: str | None = None,
        title: str = "inline_text",
        source_ref: str = "",
    ) -> RagIngestResponse:
        collection = collection_id or rag_settings.default_collection
        final_title = title
        if not final_title or final_title == "inline_text":
            final_title = f"文本入库 {datetime.now().strftime('%m-%d %H:%M')}"
        return await self._ingest_content(
            text,
            collection_id=collection,
            title=final_title,
            source_type="text",
            source_ref=source_ref or final_title,
        )

    async def _ingest_content(
        self,
        content: str,
        *,
        collection_id: str,
        title: str,
        source_type: str,
        source_ref: str,
    ) -> RagIngestResponse:
        chunks = chunk_text(
            content,
            chunk_size=rag_settings.chunk_size,
            chunk_overlap=rag_settings.chunk_overlap,
        )
        if not chunks:
            raise ValueError("文档内容为空，无法入库")

        doc_id = self.meta.create_document(
            collection_id=collection_id,
            title=title,
            source_type=source_type,
            source_ref=source_ref,
            char_count=len(content),
            chunk_count=len(chunks),
        )

        metadatas = [
            {
                "doc_id": doc_id,
                "title": title,
                "url": source_ref,
                "chunk_index": index,
            }
            for index in range(len(chunks))
        ]
        chunk_ids = self.store.add_chunks(collection_id, doc_id=doc_id, chunks=chunks, metadatas=metadatas)
        self.meta.add_chunks(doc_id, collection_id, chunk_ids)

        response = RagIngestResponse(
            doc_id=doc_id,
            collection_id=collection_id,
            title=title,
            chunk_count=len(chunks),
            char_count=len(content),
        )

        if self.server:
            await self.server.send_message(
                msg_type="execution_log",
                message={
                    "summary": f"入库完成: {title}",
                    "status": "completed",
                    "log": [
                        f"collection={collection_id}",
                        f"doc_id={doc_id}",
                        f"chunks={len(chunks)}",
                    ],
                    "payload": response.model_dump(),
                },
            )
        return response

    async def query(self, req: RagQueryRequest) -> RagQueryResponse:
        started = time.perf_counter()
        collection_id = req.collection_id or rag_settings.default_collection
        top_k = req.top_k if req.top_k is not None else rag_settings.top_k
        min_score = req.min_score if req.min_score is not None else rag_settings.min_score
        summarize = req.summarize if req.summarize is not None else rag_settings.summarize

        raw_sources = self.retriever.retrieve(
            req.query,
            collection_id=collection_id,
            top_k=top_k,
            min_score=min_score,
        )

        if summarize:
            answer = await self.assistant.summarize_answer(req.query, raw_sources)
            mode = "summarized"
        else:
            answer = self.assistant.direct_answer(req.query, raw_sources)
            mode = "direct"

        latency_ms = int((time.perf_counter() - started) * 1000)
        sources = raw_sources if req.include_sources else []

        return RagQueryResponse(
            query=req.query,
            answer=answer,
            sources=sources,
            mode=mode,
            retrieval=RetrievalMeta(
                collection_id=collection_id,
                top_k=top_k,
                min_score=min_score,
                chunks_retrieved=len(raw_sources),
                chunks_used=len(raw_sources),
                summarize=summarize,
                latency_ms=latency_ms,
            ),
        )

    async def chat(
        self,
        message: str,
        *,
        session_id: str = "default",
        collection_id: str | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
        summarize: bool | None = None,
        push: bool = False,
    ) -> RagChatResponse:
        self.memory.create_session(session_id, title=session_id)
        history = self.memory.get_messages(session_id)

        started = time.perf_counter()
        coll = collection_id or rag_settings.default_collection
        k = top_k if top_k is not None else rag_settings.top_k
        score_floor = min_score if min_score is not None else rag_settings.min_score
        use_summarize = summarize if summarize is not None else rag_settings.summarize

        raw_sources = self.retriever.retrieve(
            message,
            collection_id=coll,
            top_k=k,
            min_score=score_floor,
        )

        if use_summarize:
            answer = await self.assistant.summarize_answer(message, raw_sources, history=history)
            mode = "summarized"
        else:
            answer = self.assistant.direct_answer(message, raw_sources)
            mode = "direct"

        latency_ms = int((time.perf_counter() - started) * 1000)
        result = RagQueryResponse(
            query=message,
            answer=answer,
            sources=raw_sources,
            mode=mode,
            retrieval=RetrievalMeta(
                collection_id=coll,
                top_k=k,
                min_score=score_floor,
                chunks_retrieved=len(raw_sources),
                chunks_used=len(raw_sources),
                summarize=use_summarize,
                latency_ms=latency_ms,
            ),
        )

        self.memory.append(session_id, "user", message)
        self.memory.append(session_id, "assistant", result.answer, metadata={"mode": result.mode})

        if push and self.server:
            await self._push_rag_result(result, session_id=session_id)

        return RagChatResponse(reply=result.answer, session_id=session_id, rag=result)

    async def _push_rag_result(self, result: RagQueryResponse, *, session_id: str) -> None:
        if not self.server:
            return
        sources_payload = [
            {
                "title": item.title,
                "url": item.url or item.doc_id,
                "score": item.score,
                "snippet": item.snippet,
                "doc_id": item.doc_id,
                "chunk_id": item.chunk_id,
                "chunk_index": item.chunk_index,
            }
            for item in result.sources
        ]
        await self.server.send_message(
            msg_type=DEFAULT_MSG_TYPE,
            message={
                "query": result.query,
                "answer": result.answer,
                "sources": sources_payload,
                "collection_id": result.retrieval.collection_id,
                "session_id": session_id,
                "mode": result.mode,
                "retrieval_meta": result.retrieval.model_dump(),
            },
        )

    def status(self) -> RagStatusResponse:
        collections = [
            RagCollectionInfo(
                collection_id=row["collection_id"],
                document_count=int(row["document_count"]),
                chunk_count=int(row["chunk_count"]),
            )
            for row in self.meta.list_collections()
        ]
        if not collections:
            chroma_count = self.store.count_chunks(rag_settings.default_collection)
            if chroma_count:
                collections.append(
                    RagCollectionInfo(
                        collection_id=rag_settings.default_collection,
                        document_count=0,
                        chunk_count=chroma_count,
                    )
                )

        return RagStatusResponse(
            default_collection=rag_settings.default_collection,
            collections=collections,
            settings={
                "top_k": rag_settings.top_k,
                "min_score": rag_settings.min_score,
                "summarize": rag_settings.summarize,
                "chunk_size": rag_settings.chunk_size,
                "chunk_overlap": rag_settings.chunk_overlap,
                "embed_model": rag_settings.embed_model,
            },
        )
