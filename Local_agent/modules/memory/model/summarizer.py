from __future__ import annotations

import logging
import re
from typing import Any

from shared.llm import get_llm_client
from modules.memory.model.prompts import SUMMARIZE_SYSTEM

logger = logging.getLogger(__name__)

_FUTURE_KEYWORDS = ("以后", "今后", "下次", "默认", "都要", "统一", "不再", "总是", "优先", "沿用")
_FORBIDDEN_EVENT_PHRASES = ("第二次", "首次", "尝试成功", "耗时")


class DialogueSummarizer:
    """将一段对话原文总结为一句可入库的记忆。"""

    def __init__(self, slot: str = "memory.summarize") -> None:
        self.slot = slot

    @staticmethod
    def extract_user_commitments(dialogue: str) -> list[str]:
        """提取含面向未来关键词的用户发言。"""
        found: list[str] = []
        for raw in dialogue.splitlines():
            line = raw.strip()
            if not line:
                continue
            if not re.match(r"^用户\s*[:：]", line):
                continue
            if any(kw in line for kw in _FUTURE_KEYWORDS):
                found.append(line)
        return found

    @staticmethod
    def _looks_like_event_log(summary: str) -> bool:
        return any(phrase in summary for phrase in _FORBIDDEN_EVENT_PHRASES)

    def _build_user_prompt(self, dialogue: str) -> str:
        commitments = self.extract_user_commitments(dialogue)
        parts = [f"对话原文：\n\n{dialogue.strip()}"]
        if commitments:
            parts.append(
                "【必须优先写进总结的用户表态】\n"
                + "\n".join(f"- {line}" for line in commitments)
                + "\n\n若存在上述表态，总结必须写出其长期规则或偏好，不得只写某次任务成败。"
            )
        parts.append("请严格按 system 要求输出 JSON。")
        return "\n\n".join(parts)

    async def summarize(self, dialogue: str) -> str | None:
        text = dialogue.strip()
        if not text:
            return None

        llm = get_llm_client(self.slot)
        user_prompt = self._build_user_prompt(text)
        commitments = self.extract_user_commitments(text)

        try:
            data = await llm.chat_json(
                [
                    {"role": "system", "content": SUMMARIZE_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ]
            )
            summary = str(data.get("summary") or "").strip()
            if not summary:
                return None

            if commitments and self._looks_like_event_log(summary):
                retry_user = (
                    user_prompt
                    + "\n\n【纠正】你上次总结仍像事件流水账。"
                    "请重写，必须体现用户在「以后/默认/统一」等方面的长期要求。"
                )
                data = await llm.chat_json(
                    [
                        {"role": "system", "content": SUMMARIZE_SYSTEM},
                        {"role": "user", "content": retry_user},
                    ]
                )
                summary = str(data.get("summary") or "").strip() or summary

            return summary or None
        except Exception:
            logger.exception("Dialogue summarize failed")
            return None
