"""DeepSeek V4 DSML tool-call markup: parse + strip from visible content.

When the API fails to convert native DSML into structured ``tool_calls``,
raw tags like ``<｜DSML｜tool_calls>`` / ``<｜DSML｜invoke …>`` leak into
``message.content``. This module recovers tool calls and cleans user-visible text.
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Fast path: any of these substrings means DSML may be present
_SENTINELS = (
    "DSML",
    "｜DSML｜",
    "|DSML|",
)

# Open/close tags: fullwidth ｜ or ASCII |, optional doubling/spacing
# Examples matched:
#   <｜DSML｜tool_calls>
#   <｜｜DSML｜｜tool_calls>
#   < | DSML | invoke name="x">
_TAG_OPEN = re.compile(
    r"<\s*[|｜]+\s*DSML\s*[|｜]+\s*"
    r"(?P<tag>tool_calls|invoke|parameter)"
    r"(?P<attrs>[^>]*)>",
    re.IGNORECASE,
)
_TAG_CLOSE = re.compile(
    r"</\s*[|｜]+\s*DSML\s*[|｜]+\s*"
    r"(?P<tag>tool_calls|invoke|parameter)\s*>",
    re.IGNORECASE,
)

_ATTR_RE = re.compile(
    r'(?P<key>[A-Za-z_][\w-]*)\s*=\s*(?P<q>["\'])(?P<val>.*?)(?P=q)',
    re.DOTALL,
)

# Hermes-style begin/end with JSON body
_BEGIN_END_CALL = re.compile(
    r"<\s*[|｜]+\s*DSML\s*[|｜]+\s*tool[_.]?call[_.]?begin\s*[|｜]*\s*>"
    r"\s*(?P<name>[^\n<|｜]+?)\s*"
    r"(?:```json\s*(?P<json_args>.*?)\s*```|(?P<raw_args>\{.*?\}))"
    r"\s*"
    r"<\s*[|｜]+\s*DSML\s*[|｜]+\s*tool[_.]?call[_.]?end\s*[|｜]*\s*>",
    re.IGNORECASE | re.DOTALL,
)


def looks_like_dsml(text: str | None) -> bool:
    if not text:
        return False
    if "DSML" not in text:
        return False
    return bool(_TAG_OPEN.search(text) or _BEGIN_END_CALL.search(text))


def _parse_attrs(attrs: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in _ATTR_RE.finditer(attrs or ""):
        out[m.group("key")] = m.group("val")
    return out


def _first_dsml_span(text: str) -> int:
    positions = []
    m = _TAG_OPEN.search(text)
    if m:
        positions.append(m.start())
    m2 = _BEGIN_END_CALL.search(text)
    if m2:
        positions.append(m2.start())
    # also catch begin markers without full match
    for pat in (
        r"<\s*[|｜]+\s*DSML\s*[|｜]+\s*tool",
        r"<\s*[|｜]+\s*DSML\s*[|｜]+\s*invoke",
    ):
        m3 = re.search(pat, text, re.IGNORECASE)
        if m3:
            positions.append(m3.start())
    return min(positions) if positions else -1


def strip_dsml(text: str | None) -> str:
    """Remove DSML blocks; keep preceding natural-language preamble."""
    if not text:
        return ""
    if "DSML" not in text:
        return text
    start = _first_dsml_span(text)
    if start < 0:
        # fallback: drop lines containing DSML tags
        lines = [ln for ln in text.splitlines() if "DSML" not in ln]
        return "\n".join(lines).strip()
    return text[:start].strip()


def _coerce_param_value(raw: str, attrs: dict[str, str]) -> Any:
    text = raw.strip()
    type_hint = (attrs.get("string") or attrs.get("type") or "").lower()
    if type_hint in ("true", "1", "string", "str"):
        return text
    if type_hint in ("false", "0") and "string" in attrs:
        # string="false" → still try JSON
        pass
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        low = text.lower()
        if low == "true":
            return True
        if low == "false":
            return False
        try:
            if "." in text:
                return float(text)
            return int(text)
        except ValueError:
            return text


def _parse_invoke_blocks(text: str) -> list[dict[str, Any]]:
    """Parse ``<…DSML…invoke name=…>`` + parameter children."""
    calls: list[dict[str, Any]] = []
    for open_m in _TAG_OPEN.finditer(text):
        if open_m.group("tag").lower() != "invoke":
            continue
        attrs = _parse_attrs(open_m.group("attrs"))
        name = (attrs.get("name") or attrs.get("tool") or "").strip()
        if not name:
            continue

        close_m = _TAG_CLOSE.search(text, open_m.end())
        # find matching </…invoke>
        end = len(text)
        pos = open_m.end()
        while True:
            cm = _TAG_CLOSE.search(text, pos)
            if not cm:
                break
            if cm.group("tag").lower() == "invoke":
                end = cm.start()
                break
            pos = cm.end()

        inner = text[open_m.end() : end]
        args: dict[str, Any] = {}
        for pm in _TAG_OPEN.finditer(inner):
            if pm.group("tag").lower() != "parameter":
                continue
            pattrs = _parse_attrs(pm.group("attrs"))
            pname = (pattrs.get("name") or "").strip()
            if not pname:
                continue
            pcm = _TAG_CLOSE.search(inner, pm.end())
            if pcm and pcm.group("tag").lower() == "parameter":
                pval = inner[pm.end() : pcm.start()]
            else:
                # unclosed: take until next tag
                nxt = _TAG_OPEN.search(inner, pm.end())
                pval = inner[pm.end() : nxt.start()] if nxt else inner[pm.end() :]
            args[pname] = _coerce_param_value(pval, pattrs)

        calls.append(
            {
                "id": f"dsml_{uuid.uuid4().hex[:10]}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": json.dumps(args, ensure_ascii=False),
                },
            }
        )
    return calls


def _parse_begin_end_blocks(text: str) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for m in _BEGIN_END_CALL.finditer(text):
        name = (m.group("name") or "").strip()
        args_raw = (m.group("json_args") or m.group("raw_args") or "{}").strip()
        if not name:
            continue
        # validate / normalize arguments JSON
        try:
            obj = json.loads(args_raw)
            args_s = json.dumps(obj, ensure_ascii=False) if isinstance(obj, dict) else args_raw
        except json.JSONDecodeError:
            args_s = args_raw
        calls.append(
            {
                "id": f"dsml_{uuid.uuid4().hex[:10]}",
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": args_s,
                },
            }
        )
    return calls


def parse_dsml_tool_calls(text: str | None) -> list[dict[str, Any]]:
    if not text or "DSML" not in text:
        return []
    calls = _parse_invoke_blocks(text)
    if not calls:
        calls = _parse_begin_end_blocks(text)
    if calls:
        logger.info("parsed %s DSML tool call(s) from content", len(calls))
    elif looks_like_dsml(text):
        logger.warning("DSML markers present but no tool calls parsed")
    return calls


def heal_dsml_message(content: str | None, tool_calls: list[dict[str, Any]] | None) -> tuple[str, list[dict[str, Any]]]:
    """
    Strip DSML from content; if structured tool_calls empty, recover from content.
    Returns (clean_content, tool_calls).
    """
    text = content or ""
    calls = list(tool_calls or [])
    if not looks_like_dsml(text) and not any("DSML" in str(c) for c in ()):
        return text, calls

    if looks_like_dsml(text):
        if not calls:
            calls = parse_dsml_tool_calls(text)
        text = strip_dsml(text)
    return text, calls
