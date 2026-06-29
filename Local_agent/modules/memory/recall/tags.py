from __future__ import annotations

import json
import re
from typing import Any

_TAG_SPLIT = re.compile(r"[,，、\s]+")


def normalize_tag(tag: str) -> str:
    return tag.strip().lower()


def normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in tags:
        t = normalize_tag(str(raw))
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def merge_tags(*groups: list[str] | None) -> list[str]:
    merged: list[str] = []
    for group in groups:
        merged.extend(group or [])
    return normalize_tags(merged)


def tags_to_csv(tags: list[str]) -> str:
    return ",".join(normalize_tags(tags))


def tags_from_metadata(meta: dict[str, Any] | None) -> list[str]:
    if not meta:
        return []
    if "tags" in meta and isinstance(meta["tags"], list):
        return normalize_tags([str(t) for t in meta["tags"]])
    raw = meta.get("tags_csv") or meta.get("tags")
    if isinstance(raw, str) and raw.strip():
        if raw.strip().startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return normalize_tags([str(t) for t in parsed])
            except json.JSONDecodeError:
                pass
        return normalize_tags(_TAG_SPLIT.split(raw))
    return []


def strip_embed_document(document: str) -> str:
    if document.startswith("tags: ") and " | " in document:
        return document.split(" | ", 1)[1].strip()
    return document.strip()


def format_embed_document(content: str, tags: list[str]) -> str:
    clean_tags = normalize_tags(tags)
    if not clean_tags:
        return content.strip()
    return f"tags: {', '.join(clean_tags)} | {content.strip()}"


def tag_match_score(query_tags: list[str], memory_tags: list[str]) -> float:
    q = {normalize_tag(t) for t in query_tags if t}
    m = {normalize_tag(t) for t in memory_tags if t}
    if not q or not m:
        return 0.0
    return len(q & m) / len(q)


def blend_relevance(vector_score: float, tag_score: float, *, vector_weight: float, tag_weight: float) -> float:
    return vector_weight * vector_score + tag_weight * tag_score
