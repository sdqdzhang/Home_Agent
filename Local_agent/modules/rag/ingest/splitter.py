"""分块调度：rule / semantic / semantic_embedding / structural。"""

from __future__ import annotations

from typing import Literal

from modules.rag.config import rag_settings
from modules.rag.ingest.splitter_rule import split_text_rule
from modules.rag.ingest.splitter_semantic import split_text_semantic
from modules.rag.ingest.splitter_semantic_embedding import split_text_semantic_embedding
from modules.rag.ingest.splitter_structural import split_text_structural
from modules.rag.ingest.types import SplitPiece
from modules.rag.model.split_judge import SemanticSplitJudge

SplitMode = Literal["rule", "semantic", "semantic_embedding", "structural"]

_ALL_MODES = ("rule", "semantic", "semantic_embedding", "structural")


def resolve_split_mode(
    *,
    split_mode: SplitMode | None = None,
    use_model: bool | None = None,
) -> SplitMode:
    """use_model=True → semantic（3B 裁判）；False → rule；否则 split_mode 或 .env 默认。"""
    if use_model is True:
        return "semantic"
    if use_model is False:
        return "rule"
    if split_mode in _ALL_MODES:
        return split_mode  # type: ignore[return-value]
    default = rag_settings.split_mode
    return default if default in _ALL_MODES else "rule"  # type: ignore[return-value]


async def split_document(
    text: str,
    *,
    split_mode: SplitMode | None = None,
    use_model: bool | None = None,
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    source_ref: str = "",
) -> tuple[list[SplitPiece], SplitMode]:
    mode = resolve_split_mode(split_mode=split_mode, use_model=use_model)
    size = chunk_size if chunk_size is not None else rag_settings.chunk_size
    overlap = chunk_overlap if chunk_overlap is not None else rag_settings.chunk_overlap

    if mode == "semantic":
        judge = SemanticSplitJudge()
        raw = await split_text_semantic(text, chunk_size=size, chunk_overlap=overlap, judge=judge)
        pieces = [SplitPiece(text=c) for c in raw]
    elif mode == "semantic_embedding":
        pieces = split_text_semantic_embedding(text, chunk_size=size, chunk_overlap=overlap)
    elif mode == "structural":
        pieces = split_text_structural(text, chunk_size=size, chunk_overlap=overlap, source_ref=source_ref)
    else:
        raw = split_text_rule(text, chunk_size=size, chunk_overlap=overlap)
        pieces = [SplitPiece(text=c) for c in raw]
    return pieces, mode
