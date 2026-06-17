from __future__ import annotations


def hard_chunk_text(text: str, *, chunk_size: int, chunk_overlap: int) -> list[str]:
    """按字符滑动窗口硬切（splitter 在段落/标题仍过长时的退化方案）。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(text):
            break
        start = max(end - chunk_overlap, start + 1)
    return chunks
