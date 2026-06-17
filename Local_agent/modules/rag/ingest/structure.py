"""Markdown 结构解析：标题路径 + 章节正文。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


@dataclass
class MarkdownBlock:
    header_path: dict[str, str] = field(default_factory=dict)
    content: str = ""


def parse_markdown_blocks(text: str) -> list[MarkdownBlock]:
    """扫描 # ~ ######，按标题层级拆成逻辑块。"""
    lines = text.split("\n")
    header_stack: list[tuple[int, str]] = []
    body_lines: list[str] = []
    blocks: list[MarkdownBlock] = []

    def flush() -> None:
        body = "\n".join(body_lines).strip()
        path = _stack_to_path(header_stack)
        if body or path:
            blocks.append(MarkdownBlock(header_path=path, content=body))
        body_lines.clear()

    for line in lines:
        match = _HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            header_stack = [item for item in header_stack if item[0] < level]
            header_stack.append((level, title))
            body_lines = [line]
        else:
            body_lines.append(line)

    flush()
    if not blocks and text.strip():
        return [MarkdownBlock(content=text.strip())]
    return blocks


def _stack_to_path(stack: list[tuple[int, str]]) -> dict[str, str]:
    return {f"Header_{index + 1}": title for index, (_, title) in enumerate(stack)}


def format_chunk_with_headers(header_path: dict[str, str], body: str) -> str:
    """检索友好：在正文前注入标题面包屑。"""
    body = body.strip()
    if not header_path:
        return body
    trail = " > ".join(header_path.values())
    if not body:
        return f"[{trail}]"
    return f"[{trail}]\n\n{body}"
