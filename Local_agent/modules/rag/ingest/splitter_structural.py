"""策略④：Markdown 结构分块（Hierarchical / Structural Chunking）。"""

from __future__ import annotations

from modules.rag.ingest.recursive_split import recursive_split_text
from modules.rag.ingest.structure import format_chunk_with_headers, parse_markdown_blocks
from modules.rag.ingest.types import SplitPiece


def split_text_structural(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    source_ref: str = "",
) -> list[SplitPiece]:
    text = text.strip()
    if not text:
        return []

    pieces: list[SplitPiece] = []
    for block in parse_markdown_blocks(text):
        body = block.content.strip()
        if not body:
            continue

        meta = dict(block.header_path)
        if source_ref:
            meta["source_ref"] = source_ref

        if len(body) <= chunk_size:
            pieces.append(
                SplitPiece(
                    text=format_chunk_with_headers(block.header_path, body),
                    metadata=meta,
                )
            )
            continue

        for sub in recursive_split_text(body, chunk_size=chunk_size, chunk_overlap=chunk_overlap):
            pieces.append(
                SplitPiece(
                    text=format_chunk_with_headers(block.header_path, sub),
                    metadata=meta,
                )
            )
    return pieces if pieces else [SplitPiece(text=text)]
