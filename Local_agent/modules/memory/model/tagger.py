from __future__ import annotations

import logging
import re

from shared.llm import get_llm_client
from modules.memory.model.prompts import TAG_SYSTEM
from modules.memory.recall.tags import merge_tags, normalize_tags

logger = logging.getLogger(__name__)

_INTENT_PREFIX = re.compile(r"^\[([^\]]+)\]")


class MemoryTagger:
    def __init__(self, slot: str = "memory.tag") -> None:
        self.slot = slot

    @staticmethod
    def intent_from_content(content: str) -> str | None:
        match = _INTENT_PREFIX.match(content.strip())
        if match:
            return match.group(1).strip()
        return None

    async def tag(self, content: str, *, kind: str = "observation", manual_tags: list[str] | None = None) -> list[str]:
        text = content.strip()
        if not text:
            return normalize_tags(manual_tags)

        llm = get_llm_client(self.slot)
        user = f"记忆类型: {kind}\n记忆内容:\n{text}"
        llm_tags: list[str] = []
        try:
            data = await llm.chat_json(
                [
                    {"role": "system", "content": TAG_SYSTEM},
                    {"role": "user", "content": user},
                ]
            )
            raw = data.get("tags") or []
            if isinstance(raw, list):
                llm_tags = [str(t) for t in raw if str(t).strip()]
        except Exception:
            logger.exception("Memory tag failed")

        prefix_intent = self.intent_from_content(text)
        prefix_tags = [prefix_intent] if prefix_intent else []
        return merge_tags(manual_tags, prefix_tags, llm_tags)
