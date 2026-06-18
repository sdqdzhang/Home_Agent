from __future__ import annotations

import logging

from shared.llm import get_llm_client
from modules.memory.model.prompts import ASSESS_SYSTEM

logger = logging.getLogger(__name__)


class ImportanceAssessor:
    def __init__(self, slot: str = "memory.assess") -> None:
        self.slot = slot

    async def rate(self, content: str) -> tuple[float, str]:
        llm = get_llm_client(self.slot)
        user = f"Memory: {content}\nRating:"
        try:
            data = await llm.chat_json(
                [
                    {"role": "system", "content": ASSESS_SYSTEM},
                    {"role": "user", "content": user},
                ]
            )
            raw = data.get("rating", 5)
            rating = float(raw)
            rating = max(1.0, min(10.0, rating))
            reason = str(data.get("reason") or "").strip()
            return rating, reason
        except Exception:
            logger.exception("Memory importance assess failed")
            return 5.0, "模型打分失败，使用默认 5 分"
