from __future__ import annotations

import logging
import re

from shared.llm import get_llm_client
from modules.memory.model.prompts import ASSESS_SYSTEM

logger = logging.getLogger(__name__)

_FUTURE_MARKERS = ("以后", "今后", "下次", "默认", "统一", "沿用", "长期", "偏好", "不再", "总是")
_RULE_MARKERS = ("要求", "选定", "确认", "规定", "必须", "规则")


def preference_score_floor(content: str) -> float | None:
    """对明显的长期偏好/规则记忆设最低分，避免小模型系统性低估。"""
    text = content.strip()
    if not text:
        return None
    has_future = any(m in text for m in _FUTURE_MARKERS)
    has_rule = any(m in text for m in _RULE_MARKERS)
    if has_future and has_rule:
        return 7.0
    if has_future and re.search(r"(选定|采用|使用).{0,20}(方案|框架|技术|栈|工具)", text):
        return 7.0
    return None


class ImportanceAssessor:
    def __init__(self, slot: str = "memory.assess") -> None:
        self.slot = slot

    async def rate(self, content: str) -> tuple[float, str]:
        llm = get_llm_client(self.slot)
        user = f"待评估记忆：\n{content.strip()}\n\n请打分："
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

            floor = preference_score_floor(content)
            if floor is not None and rating < floor:
                reason = f"{reason}；检测到长期偏好/规则，不低于 {floor:.0f} 分".strip("；")
                rating = floor

            return rating, reason
        except Exception:
            logger.exception("Memory importance assess failed")
            floor = preference_score_floor(content)
            return floor or 5.0, "模型打分失败，使用规则兜底或默认 5 分"
