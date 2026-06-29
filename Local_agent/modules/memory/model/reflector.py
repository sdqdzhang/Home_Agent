from __future__ import annotations

import logging
import re
from typing import Any

from shared.llm import get_llm_client
from modules.memory.model.prompts import REFLECT_SYSTEM

logger = logging.getLogger(__name__)

_TAG_RE = re.compile(r"^\[([^\]]+)\]\s*")


class MemoryReflector:
    def __init__(self, slot: str = "memory.reflect") -> None:
        self.slot = slot

    @staticmethod
    def format_content(tag: str, insight: str) -> str:
        tag = tag.strip().strip("[]")
        body = insight.strip()
        if body.startswith("["):
            match = _TAG_RE.match(body)
            if match:
                return body
        return f"[{tag}] {body}"

    async def synthesize(self, observations: list[dict[str, Any]]) -> dict[str, str] | None:
        """多条流水账 → 一条带语义标签的洞察文本。"""
        if not observations:
            return None

        lines = []
        for item in observations:
            lines.append(
                f"- [{item.get('created_at', '')}] "
                f"(importance={item.get('importance', '?')}) {item.get('content', '')}"
            )
        user = "Recent working memory observations:\n" + "\n".join(lines)

        llm = get_llm_client(self.slot)
        try:
            data = await llm.chat_json(
                [
                    {"role": "system", "content": REFLECT_SYSTEM},
                    {"role": "user", "content": user},
                ]
            )
            tag = str(data.get("tag") or "深度反思").strip().strip("[]") or "深度反思"
            insight = str(data.get("insight") or "").strip()
            if not insight:
                return None
            content = self.format_content(tag, insight)
            return {"tag": tag, "insight": insight, "content": content}
        except Exception:
            logger.exception("Memory reflect failed")
            return None
