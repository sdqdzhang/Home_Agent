"""文本单元切分：标题 / 段落 / 句子（供 rule 与 semantic 策略复用）。"""

from __future__ import annotations

import re

_HEADING_LINE_RE = re.compile(r"^#{1,6}\s+\S")
_PARAGRAPH_SPLIT_RE = re.compile(r"\n\s*\n+")
# 中英文句号、问号、叹号、换行后切句
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[。！？.!?…])\s*|\n+")


def split_by_headings(text: str) -> list[str]:
    """在 Markdown 标题行处切分，标题保留在 section 开头。"""
    lines = text.split("\n")
    sections: list[str] = []
    current: list[str] = []

    for line in lines:
        if _HEADING_LINE_RE.match(line):
            if current:
                block = "\n".join(current).strip()
                if block:
                    sections.append(block)
            current = [line]
        else:
            current.append(line)

    if current:
        block = "\n".join(current).strip()
        if block:
            sections.append(block)

    return sections if sections else [text.strip()]


def split_by_paragraphs(text: str) -> list[str]:
    """按双换行切分段落。"""
    parts = _PARAGRAPH_SPLIT_RE.split(text)
    return [part.strip() for part in parts if part.strip()]


def split_by_sentences(text: str) -> list[str]:
    """按句号/问号/叹号/换行切分句子，保留标点。"""
    parts = _SENTENCE_SPLIT_RE.split(text)
    return [part.strip() for part in parts if part.strip()]
