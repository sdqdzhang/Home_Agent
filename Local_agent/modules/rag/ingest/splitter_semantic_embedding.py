"""策略③：句子向量余弦距离断点分块（Semantic Embedding Chunking）。"""

from __future__ import annotations

import math

from modules.rag.config import rag_settings
from modules.rag.ingest.types import SplitPiece
from modules.rag.ingest.units import split_by_sentences
from modules.rag.index.embedder import OllamaEmbedder


def split_text_semantic_embedding(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    embedder: OllamaEmbedder | None = None,
) -> list[SplitPiece]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= rag_settings.min_chunk_size:
        return [SplitPiece(text=text)]

    sentences = split_by_sentences(text)
    if len(sentences) <= 1:
        return [SplitPiece(text=text)]

    embedder = embedder or OllamaEmbedder()
    vectors = embedder.embed(sentences)
    if len(vectors) != len(sentences):
        return [SplitPiece(text=text)]

    breakpoints = _find_breakpoints(vectors)
    raw_chunks = _build_chunks_from_breakpoints(sentences, breakpoints)
    merged = _merge_small_chunks(raw_chunks, min_size=rag_settings.min_chunk_size)
    final: list[SplitPiece] = []
    for chunk in merged:
        if len(chunk) > chunk_size:
            from modules.rag.ingest.chunker import hard_chunk_text

            for piece in hard_chunk_text(chunk, chunk_size=chunk_size, chunk_overlap=chunk_overlap):
                final.append(SplitPiece(text=piece))
        else:
            final.append(SplitPiece(text=chunk))
    return final


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    similarity = dot / (norm_a * norm_b)
    return max(0.0, 1.0 - similarity)


def _find_breakpoints(vectors: list[list[float]]) -> set[int]:
    if len(vectors) < 2:
        return set()

    distances = [_cosine_distance(vectors[i], vectors[i + 1]) for i in range(len(vectors) - 1)]
    threshold = rag_settings.embed_breakpoint_threshold

    percentile = rag_settings.embed_breakpoint_percentile
    if percentile and distances:
        sorted_d = sorted(distances)
        idx = min(len(sorted_d) - 1, int(len(sorted_d) * percentile / 100))
        pct_val = sorted_d[idx]
        threshold = max(threshold, pct_val)

    breakpoints: set[int] = set()
    for index, distance in enumerate(distances):
        if distance >= threshold:
            breakpoints.add(index + 1)
    return breakpoints


def _build_chunks_from_breakpoints(sentences: list[str], breakpoints: set[int]) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    for index, sentence in enumerate(sentences):
        if index in breakpoints and current:
            chunks.append(_join_sentences(current))
            current = []
        current.append(sentence)
    if current:
        chunks.append(_join_sentences(current))
    return [c for c in chunks if c.strip()]


def _merge_small_chunks(chunks: list[str], *, min_size: int) -> list[str]:
    if not chunks:
        return []
    merged: list[str] = []
    buffer = ""
    for chunk in chunks:
        if not buffer:
            buffer = chunk
            continue
        if len(buffer) < min_size:
            buffer = _join_sentences([buffer, chunk])
        else:
            merged.append(buffer)
            buffer = chunk
    if buffer:
        if merged and len(buffer) < min_size:
            merged[-1] = _join_sentences([merged[-1], buffer])
        else:
            merged.append(buffer)
    return merged


def _join_sentences(parts: list[str]) -> str:
    if not parts:
        return ""
    result = parts[0]
    for part in parts[1:]:
        if result and result[-1].isascii() and part and part[0].isascii():
            result = f"{result} {part}"
        else:
            result = f"{result}{part}"
    return result.strip()
