from __future__ import annotations

import re

_FENCE_PATTERN = re.compile(
    r"```[^\n]*\n(.*?)```",
    re.DOTALL,
)


def extract_fenced_blocks(text: str) -> list[str]:
    """提取 Markdown 围栏代码块正文（不含 ``` 行）。"""
    blocks = [_untrim_block(m.group(1)) for m in _FENCE_PATTERN.finditer(text)]
    return [block for block in blocks if block]


def strip_fenced_blocks(text: str) -> str:
    """去掉围栏代码块，保留自然语言指令部分。"""
    stripped = _FENCE_PATTERN.sub("", text)
    lines = [line.rstrip() for line in stripped.splitlines()]
    return "\n".join(lines).strip()


def pick_file_body(
    *,
    file_content: str | None = None,
    fenced_blocks: list[str] | None = None,
    llm_content: str | None = None,
) -> tuple[str | None, str]:
    """
    解析 file.write 正文来源。
    返回 (body, source)，source 为 payload | fenced_block | llm | none。
    """
    if file_content is not None:
        return file_content, "payload"

    blocks = fenced_blocks or []
    if blocks:
        if len(blocks) == 1:
            return blocks[0], "fenced_block"
        return max(blocks, key=len), "fenced_block"

    if llm_content is not None:
        return llm_content, "llm"

    return None, "none"


def _untrim_block(text: str) -> str:
    # 保留首尾空行语义，仅去掉围栏内侧最多一行换行
    if text.endswith("\n"):
        text = text[:-1]
    return text
