from __future__ import annotations

import logging
from typing import Any

from shared.llm import get_llm_client
from modules.security.model.prompts import AUTO_APPROVE_SYSTEM, CHAT_SYSTEM, JUDGE_SYSTEM

logger = logging.getLogger(__name__)


class SecurityJudge:
    def __init__(self, slot: str = "security.judge") -> None:
        self.slot = slot

    async def should_escalate(self, command: str, purpose: str, rule_reason: str) -> tuple[bool, str]:
        llm = get_llm_client(self.slot)
        user = (
            f"命令: {command}\n"
            f"目的: {purpose or '（未说明）'}\n"
            f"规则判定: {rule_reason}\n"
            "请判断是否应升为红色。"
        )
        try:
            data = await llm.chat_json(
                [
                    {"role": "system", "content": JUDGE_SYSTEM},
                    {"role": "user", "content": user},
                ]
            )
            escalate = bool(data.get("escalate"))
            reason = str(data.get("reason") or "").strip() or "模型未给出原因"
            return escalate, reason
        except Exception:
            logger.exception("Security judge failed")
            return True, "模型判定失败，保守升红"


class SecurityAutoApprover:
    def __init__(self, slot: str = "security.auto_approve") -> None:
        self.slot = slot

    async def decide(
        self,
        command: str,
        purpose: str,
        *,
        risk_level: str,
        risk_source: str,
        rule_reason: str,
    ) -> tuple[bool, str]:
        llm = get_llm_client(self.slot)
        user = (
            f"命令: {command}\n"
            f"目的: {purpose or '（未说明）'}\n"
            f"风险等级: {risk_level}\n"
            f"风险来源: {risk_source}\n"
            f"说明: {rule_reason}\n"
            "请判断是否批准执行。"
        )
        try:
            data = await llm.chat_json(
                [
                    {"role": "system", "content": AUTO_APPROVE_SYSTEM},
                    {"role": "user", "content": user},
                ]
            )
            approved = bool(data.get("approved"))
            reason = str(data.get("reason") or "").strip() or "模型未给出原因"
            return approved, reason
        except Exception:
            logger.exception("Security auto approve failed")
            return False, "模型自动审批失败，默认拒绝"


class SecurityAssistant:
    def __init__(self, slot: str = "security.chat") -> None:
        self.slot = slot

    async def chat(
        self,
        user_message: str,
        history: list[dict[str, str]],
        *,
        context: str,
    ) -> str:
        llm = get_llm_client(self.slot)
        messages: list[dict[str, Any]] = [{"role": "system", "content": f"{CHAT_SYSTEM}\n\n{context}"}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return await llm.chat(messages)
