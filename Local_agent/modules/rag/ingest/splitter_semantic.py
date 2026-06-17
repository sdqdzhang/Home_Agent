"""语义分块：按句子扫描，由 3B 模型判断主题切换点。

在 Markdown 标题 section 内逐句合并；超过 chunk_size 强制切分；
相邻句子边界处调用 SemanticSplitJudge（YES → 新块）。
"""

from __future__ import annotations

import logging

from modules.rag.ingest.chunker import hard_chunk_text
from modules.rag.ingest.units import split_by_headings, split_by_sentences
from modules.rag.model.split_judge import SemanticSplitJudge

logger = logging.getLogger(__name__)


async def split_text_semantic(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    judge: SemanticSplitJudge | None = None,
) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]

    judge = judge or SemanticSplitJudge()
    chunks: list[str] = []

    for section in split_by_headings(text):
        section = section.strip()
        if not section:
            continue
        section_chunks = await _semantic_merge_sentences(
            section,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            judge=judge,
        )
        chunks.extend(section_chunks)
    return chunks


async def _semantic_merge_sentences(
    text: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
    judge: SemanticSplitJudge,
) -> list[str]:
    sentences = split_by_sentences(text)
    if not sentences:
        return [text] if text.strip() else []
    if len(sentences) == 1:
        sent = sentences[0]
        if len(sent) <= chunk_size:
            return [sent]
        return hard_chunk_text(sent, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    chunks: list[str] = []
    current = sentences[0]

    for next_sent in sentences[1:]:
        joined = _join_sentences(current, next_sent)
        force_split = len(joined) > chunk_size

        if force_split:
            if len(current) > chunk_size:
                chunks.extend(hard_chunk_text(current, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
            else:
                chunks.append(current.strip())
            current = next_sent
            continue

        try:
            is_switch = await judge.topic_switch(current, next_sent)
        except Exception as exc:
            logger.warning("语义分块模型调用失败，该边界按 NO 处理: %s", exc)
            is_switch = False

        if is_switch:
            chunks.append(current.strip())
            current = next_sent
        else:
            current = joined

    if current.strip():
        if len(current) > chunk_size:
            chunks.extend(hard_chunk_text(current, chunk_size=chunk_size, chunk_overlap=chunk_overlap))
        else:
            chunks.append(current.strip())
    return chunks


def _join_sentences(left: str, right: str) -> str:
    if not left:
        return right
    if not right:
        return left
    # 中文场景直接拼接；英文保留空格
    if left[-1].isascii() and right[0].isascii():
        return f"{left} {right}"
    return f"{left}{right}"
