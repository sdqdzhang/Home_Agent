from __future__ import annotations

import json
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

_FENCE_RE = re.compile(
    r"```(?:json|JSON)?\s*\n?(.*?)```",
    re.DOTALL,
)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")
_SMART_QUOTES = str.maketrans({
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
})


def strict_loads(raw: str) -> Any:
    return json.loads(raw)


def strip_code_fences(text: str) -> str:
    text = text.strip()
    match = _FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def extract_json_slice(text: str) -> str | None:
    """截取首个对象/数组字面量；找不到则返回 None。"""
    obj_start = text.find("{")
    arr_start = text.find("[")
    candidates: list[tuple[int, str]] = []
    if obj_start >= 0:
        end = text.rfind("}")
        if end > obj_start:
            candidates.append((obj_start, text[obj_start : end + 1]))
    if arr_start >= 0:
        end = text.rfind("]")
        if end > arr_start:
            candidates.append((arr_start, text[arr_start : end + 1]))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def strip_trailing_commas(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = _TRAILING_COMMA_RE.sub(r"\1", text)
    return text


def normalize_quotes(text: str) -> str:
    return text.translate(_SMART_QUOTES)


def heuristic_prepare(raw: str) -> str:
    text = raw.strip().lstrip("\ufeff")
    text = normalize_quotes(text)
    text = strip_code_fences(text)
    sliced = extract_json_slice(text)
    if sliced is not None:
        text = sliced
    return strip_trailing_commas(text)


def heuristic_loads(raw: str) -> Any:
    return json.loads(heuristic_prepare(raw))


def library_loads(raw: str, *, enabled: bool = True) -> Any:
    if not enabled:
        raise RuntimeError("json_repair disabled")
    try:
        from json_repair import repair_json
    except ImportError as exc:
        raise RuntimeError("json_repair not installed") from exc

    prepared = heuristic_prepare(raw)
    for candidate in (prepared, raw.strip()):
        if not candidate:
            continue
        obj = repair_json(candidate, return_objects=True)
        if isinstance(obj, (dict, list)):
            return obj
        if isinstance(obj, str):
            try:
                parsed = json.loads(obj)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, (dict, list)):
                return parsed
    raise json.JSONDecodeError("json_repair produced no object/array", raw, 0)


_Stage = Callable[[str], Any]


def try_parse_pipeline(
    raw: str,
    *,
    repair_enabled: bool = True,
) -> tuple[Any | None, str]:
    """
    按 strict → heuristic → json_repair 尝试解析。
    成功返回 (obj, "")；失败返回 (None, last_error)。
    """
    if raw is None:
        return None, "empty: raw is None"
    text = str(raw)
    if not text.strip():
        return None, "empty: blank response"

    stages: list[tuple[str, _Stage]] = [
        ("strict", strict_loads),
        ("heuristic", heuristic_loads),
    ]
    if repair_enabled:
        stages.append(("repair", lambda s: library_loads(s, enabled=True)))

    last_err = "unknown"
    for name, stage in stages:
        try:
            obj = stage(text)
        except Exception as exc:
            last_err = f"{name}: {exc}"
            logger.debug("json parse stage %s failed: %s", name, exc)
            continue
        if isinstance(obj, (dict, list)):
            if name != "strict":
                logger.info("json parse recovered via stage=%s", name)
            return obj, ""
        last_err = f"{name}: expected object/array, got {type(obj).__name__}"
    return None, last_err


def as_json_object(obj: Any) -> dict[str, Any] | None:
    return obj if isinstance(obj, dict) else None
