from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from modules.rag.schemas import (
    RagChatRequest,
    RagIngestFileRequest,
    RagIngestTextRequest,
    RagQueryRequest,
)

router = APIRouter(prefix="/rag", tags=["rag"])


def _get_service():
    from app.main import rag_service

    if rag_service is None:
        raise HTTPException(503, "RAG service not ready")
    return rag_service


@router.get("/status")
def rag_status() -> dict[str, Any]:
    return _get_service().status().model_dump()


@router.post("/query")
async def rag_query(req: RagQueryRequest) -> dict[str, Any]:
    return (await _get_service().query(req)).model_dump()


@router.post("/chat")
async def rag_chat(req: RagChatRequest) -> dict[str, Any]:
    result = await _get_service().chat(
        req.message,
        session_id=req.session_id,
        collection_id=req.collection_id,
        top_k=req.top_k,
        min_score=req.min_score,
        summarize=req.summarize,
    )
    return result.model_dump()


@router.post("/ingest/file")
async def rag_ingest_file(req: RagIngestFileRequest) -> dict[str, Any]:
    try:
        result = await _get_service().ingest_file(req.path, collection_id=req.collection_id, title=req.title)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return result.model_dump()


@router.post("/ingest/text")
async def rag_ingest_text(req: RagIngestTextRequest) -> dict[str, Any]:
    try:
        result = await _get_service().ingest_text(
            req.text,
            collection_id=req.collection_id,
            title=req.title,
            source_ref=req.source_ref,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result.model_dump()
