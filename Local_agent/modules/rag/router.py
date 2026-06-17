from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from modules.rag.schemas import (
    RagChatRequest,
    RagDeleteChunksRequest,
    RagDeleteCollectionRequest,
    RagDeleteDocumentRequest,
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
        result = await _get_service().ingest_file(
            req.path,
            collection_id=req.collection_id,
            title=req.title,
            split_mode=req.split_mode,
            use_model_split=req.use_model_split,
        )
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
            split_mode=req.split_mode,
            use_model_split=req.use_model_split,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return result.model_dump()


@router.get("/documents")
def rag_list_documents(collection_id: str | None = None, limit: int = 100) -> dict[str, Any]:
    return {"documents": _get_service().list_documents(collection_id, limit=limit)}


@router.post("/delete/chunks")
def rag_delete_chunks(req: RagDeleteChunksRequest) -> dict[str, Any]:
    try:
        return _get_service().delete_chunks(req.chunk_ids, collection_id=req.collection_id).model_dump()
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/delete/document")
def rag_delete_document(req: RagDeleteDocumentRequest) -> dict[str, Any]:
    try:
        return _get_service().delete_document(req.doc_id, collection_id=req.collection_id).model_dump()
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/delete/collection")
def rag_delete_collection(req: RagDeleteCollectionRequest) -> dict[str, Any]:
    if not req.collection_id.strip():
        raise HTTPException(400, "collection_id required")
    return _get_service().drop_collection(req.collection_id).model_dump()
