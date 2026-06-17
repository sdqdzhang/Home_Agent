"""规则分块：贪婪合并段落，接近 chunk_size 上限时再切。

沿 Markdown 标题边界 → 段落（\\n\\n）→ 不断合并，直到再加一段会超过上限；
单段超长时退化到 hard_chunk_text。
"""

from __future__ import annotations

from modules.rag.ingest.chunker import hard_chunk_text
from modules.rag.ingest.units import split_by_headings, split_by_paragraphs


def split_text_rule(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    for section in split_by_headings(text):
        section = section.strip()
        if not section:
            continue
        chunks.extend(_greedy_merge_paragraphs(section, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
    return chunks


def _greedy_merge_paragraphs(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    paragraphs = split_by_paragraphs(text)
    if not paragraphs:
        return [text] if text.strip() else []

    chunks: list[str] = []
    buffer = ""

    for para in paragraphs:
        if len(para) > chunk_size:
            if buffer:
                chunks.append(buffer.strip())
                buffer = ""
            chunks.extend(hard_chunk_text(para, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
            continue

        if not buffer:
            buffer = para
            continue

        joined = f"{buffer}\n\n{para}"
        if len(joined) <= chunk_size:
            buffer = joined
        else:
            chunks.append(buffer.strip())
            buffer = para

    if buffer:
        chunks.append(buffer.strip())
    return chunks
