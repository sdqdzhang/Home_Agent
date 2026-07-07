from __future__ import annotations

import re

_SEARCH_VERB = re.compile(r"(?:查找|搜索|搜|find|grep)", re.IGNORECASE)
_QUOTED_QUERY_PATTERNS = (
    re.compile(r"[「『]([^」』]+)[」』]"),
    re.compile(r'"([^"]+)"'),
    re.compile(r"'([^']+)'"),
    re.compile(r"`([^`]+)`"),
)

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


def _looks_like_path(fragment: str) -> bool:
    s = fragment.strip()
    if not s or len(s) > 260:
        return True
    if re.match(r"[A-Za-z]:", s):
        return True
    if "/" in s or "\\" in s:
        return True
    return False


def extract_search_query_from_text(text: str) -> str | None:
    """从自然语言指令中提取内容搜索关键词（模型漏填 query 时的兜底）。"""
    text = (text or "").strip()
    if not text:
        return None

    verb_end = -1
    for m in _SEARCH_VERB.finditer(text):
        verb_end = m.end()

    quoted: list[tuple[int, str]] = []
    for pattern in _QUOTED_QUERY_PATTERNS:
        for m in pattern.finditer(text):
            query = m.group(1).strip()
            if query and not _looks_like_path(query):
                quoted.append((m.start(), query))

    if quoted:
        after_verb = [item for item in quoted if item[0] >= verb_end] if verb_end >= 0 else []
        return (after_verb[0] if after_verb else quoted[-1])[1]

    if verb_end < 0:
        return None

    tail = text[verb_end:].strip()
    tail = re.sub(r"^[「『\"'`（(]+", "", tail)
    tail = re.sub(r"[」』\"'`）)]+$", "", tail).strip("：:")
    if not tail or _looks_like_path(tail):
        return None
    if len(tail) <= 80:
        return tail
    first = tail.split()[0] if tail.split() else ""
    return first if first and not _looks_like_path(first) else None
