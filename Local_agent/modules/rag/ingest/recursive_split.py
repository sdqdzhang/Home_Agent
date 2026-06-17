"""递归字符切分：\\n\\n → \\n → 空格 → 硬切（结构分块兜底）。"""

from __future__ import annotations

from modules.rag.ingest.chunker import hard_chunk_text


def recursive_split_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    for separator in ("\n\n", "\n", " "):
        parts = _split_keep_separator(text, separator)
        if len(parts) > 1:
            merged = _merge_parts(parts, chunk_size=chunk_size)
            if all(len(p) <= chunk_size for p in merged):
                return _apply_overlap(merged, chunk_overlap=chunk_overlap, chunk_size=chunk_size)

    return hard_chunk_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)


def _split_keep_separator(text: str, separator: str) -> list[str]:
    if separator not in text:
        return [text]
    raw = text.split(separator)
    parts: list[str] = []
    for index, part in enumerate(raw):
        piece = part.strip()
        if not piece:
            continue
        if index < len(raw) - 1 and separator == " ":
            parts.append(piece)
        elif index < len(raw) - 1:
            parts.append(piece)
        else:
            parts.append(piece)
    return parts if parts else [text]


def _merge_parts(parts: list[str], *, chunk_size: int) -> list[str]:
    chunks: list[str] = []
    buffer = ""
    for part in parts:
        if len(part) > chunk_size:
            if buffer:
                chunks.append(buffer.strip())
                buffer = ""
            chunks.append(part)
            continue
        candidate = f"{buffer} {part}".strip() if buffer else part
        if len(candidate) <= chunk_size:
            buffer = candidate
        else:
            if buffer:
                chunks.append(buffer.strip())
            buffer = part
    if buffer:
        chunks.append(buffer.strip())
    return chunks


def _apply_overlap(chunks: list[str], *, chunk_overlap: int, chunk_size: int) -> list[str]:
    if chunk_overlap <= 0 or len(chunks) <= 1:
        return chunks
    # 结构分块优先保持边界，仅在单块超长时 overlap；此处直接返回
    return chunks
