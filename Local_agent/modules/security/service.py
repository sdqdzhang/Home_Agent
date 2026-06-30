from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from shared.server_center.client import ServerCenterClient
from modules.security import MODULE_ALIASES, MODULE_NAME, SECURITY_LISTS_ACTIONS, YELLOW_LOG_MSG_TYPE
from modules.security.config import security_settings
from modules.security.lists_config import SecurityListsConfig
from modules.security.model import SecurityAssistant, SecurityAutoApprover, SecurityJudge
from modules.security.rules import evaluate_rules, reload_lists
from modules.security.schemas import CheckRequest, CheckResult, RiskLevel
from modules.security.storage import SecurityAuditStore

logger = logging.getLogger(__name__)


@dataclass
class _PendingApproval:
    check_id: str
    approval_msg_id: str
    future: asyncio.Future[bool] = field(repr=False)


class SecurityService:
    """安全检查：规则判定、黄色模型升红、红色用户审批。"""

    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        security_settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.server = server_client
        self.audit = SecurityAuditStore(security_settings.db_path)
        self.judge = SecurityJudge()
        self.auto_approver = SecurityAutoApprover()
        self.assistant = SecurityAssistant()
        self.lists_config = SecurityListsConfig()
        self._pending: dict[str, _PendingApproval] = {}
        self._lock = asyncio.Lock()

    def status_payload(self) -> dict[str, Any]:
        lists = reload_lists()
        return {
            "lists": lists,
            "lists_dir": str(security_settings.lists_dir),
            "approval_timeout_seconds": security_settings.approval_timeout_seconds,
            "pending_count": len(self._pending),
            "yellow_records": self.audit.list_yellow_records(limit=20),
            "approval_records": self.audit.list_approval_records(limit=20),
            "pending_approvals": self.audit.list_pending_approvals(),
        }

    async def check(self, request: CheckRequest | dict[str, Any]) -> CheckResult:
        if isinstance(request, dict):
            request = CheckRequest.model_validate(request)

        check_id = f"sec_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        evaluation = evaluate_rules(request.command)

        if evaluation.risk_level == "green":
            return CheckResult(
                allowed=True,
                risk_level="green",
                check_id=check_id,
                reason=evaluation.reason,
                risk_source="rule",
            )

        if evaluation.risk_level == "yellow":
            return await self._handle_yellow(request, check_id, evaluation.reason)

        return await self._handle_red(
            request,
            check_id,
            reason=evaluation.reason,
            risk_source="rule",
        )

    async def _handle_yellow(self, request: CheckRequest, check_id: str, rule_reason: str) -> CheckResult:
        escalate = False
        model_reason = ""

        if security_settings.use_model_for_yellow:
            escalate, model_reason = await self.judge.should_escalate(
                request.command,
                request.purpose,
                rule_reason,
            )
        else:
            model_reason = "已关闭黄色模型判定"

        if escalate:
            self.audit.add_yellow_record(
                check_id=check_id,
                command=request.command,
                purpose=request.purpose,
                caller_module=request.caller_module,
                rule_reason=rule_reason,
                escalated=True,
                model_reason=model_reason,
                allowed=False,
            )
            await self._push_yellow_log(
                check_id,
                request.command,
                request.purpose,
                rule_reason,
                escalated=True,
                model_reason=model_reason,
            )
            return await self._handle_red(
                request,
                check_id,
                reason=model_reason or rule_reason,
                risk_source="model",
            )

        self.audit.add_yellow_record(
            check_id=check_id,
            command=request.command,
            purpose=request.purpose,
            caller_module=request.caller_module,
            rule_reason=rule_reason,
            escalated=False,
            model_reason=model_reason,
            allowed=True,
        )
        await self._push_yellow_log(
            check_id,
            request.command,
            request.purpose,
            rule_reason,
            escalated=False,
            model_reason=model_reason,
        )
        return CheckResult(
            allowed=True,
            risk_level="yellow",
            check_id=check_id,
            reason=model_reason or rule_reason,
            risk_source="model",
        )

    async def _handle_red(
        self,
        request: CheckRequest,
        check_id: str,
        *,
        reason: str,
        risk_source: str,
    ) -> CheckResult:
        if not self.server:
            return CheckResult(
                allowed=False,
                risk_level="red",
                check_id=check_id,
                reason="需要用户审批但未连接 Server Center",
                risk_source=risk_source,
            )

        expires_at = int(time.time()) + security_settings.approval_timeout_seconds
        text = f"申请执行命令，是否允许？\n`{request.command}`"
        if request.purpose:
            text = f"{request.purpose}\n\n{text}"

        approval_msg_id = f"sec_appr_{check_id}"
        push = await self.server.send_message(
            msg_type="approval_request",
            message={
                "text": text,
                "payload": {
                    "check_id": check_id,
                    "command": request.command,
                    "purpose": request.purpose,
                    "risk_level": "red",
                    "risk_source": risk_source,
                    "caller_module": request.caller_module,
                    "expires_at": expires_at,
                },
            },
            msg_id=approval_msg_id,
        )
        approval_msg_id = self.server.message_id_from_response(push, approval_msg_id)

        self.audit.upsert_approval_record(
            check_id=check_id,
            approval_msg_id=approval_msg_id,
            command=request.command,
            purpose=request.purpose,
            caller_module=request.caller_module,
            risk_level="red",
            risk_source=risk_source,
            status="pending",
            reason=reason,
        )

        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        self._pending[approval_msg_id] = _PendingApproval(
            check_id=check_id,
            approval_msg_id=approval_msg_id,
            future=future,
        )

        try:
            allowed = await asyncio.wait_for(
                future,
                timeout=security_settings.approval_timeout_seconds,
            )
        except asyncio.TimeoutError:
            self._pending.pop(approval_msg_id, None)
            self.audit.resolve_approval(approval_msg_id, status="timeout", reason="审批超时")
            return CheckResult(
                allowed=False,
                risk_level="red",
                check_id=check_id,
                reason="审批超时",
                approval_id=approval_msg_id,
                risk_source="timeout",
            )
        finally:
            self._pending.pop(approval_msg_id, None)

        status = "approved" if allowed else "rejected"
        self.audit.resolve_approval(
            approval_msg_id,
            status=status,
            reason="用户已批准" if allowed else "用户已拒绝",
        )
        return CheckResult(
            allowed=allowed,
            risk_level="red",
            check_id=check_id,
            reason="用户已批准" if allowed else "用户已拒绝",
            approval_id=approval_msg_id,
            risk_source="user",
        )

    async def handle_ws_event(self, data: dict[str, Any]) -> None:
        status = data.get("status")
        msg_id = data.get("id", "")
        if status in ("approved", "rejected"):
            pending = self._pending.get(msg_id)
            if pending is None:
                payload = (data.get("message") or {}).get("payload") or {}
                check_id = payload.get("check_id")
                if check_id:
                    for item in self._pending.values():
                        if item.check_id == check_id:
                            pending = item
                            msg_id = item.approval_msg_id
                            break
            if pending and not pending.future.done():
                response = data.get("response") or {}
                approved = status == "approved" or bool(response.get("approved"))
                pending.future.set_result(approved)
            return

        if data.get("name") != "user_ui":
            return
        target = data.get("target", "")
        if target not in MODULE_ALIASES:
            return

        msg_type = data.get("msg_type", "text")
        message = data.get("message") or {}
        msg_id = data.get("id", "")

        if msg_type != "text":
            return

        payload = message.get("payload") or {}
        action = payload.get("action")

        if action == "auto_approve":
            if payload.get("all"):
                await self.run_auto_approve_all()
                return
            approval_id = payload.get("approval_id") or payload.get("check_id")
            if approval_id:
                await self.run_auto_approve(
                    approval_id,
                    command=str(payload.get("command") or ""),
                    purpose=str(payload.get("purpose") or ""),
                    risk_level=str(payload.get("risk_level") or "red"),
                    risk_source=str(payload.get("risk_source") or "rule"),
                    rule_reason=str(payload.get("rule_reason") or payload.get("reason") or ""),
                )
            return

        if action in SECURITY_LISTS_ACTIONS:
            await self.lists_config.handle(self.server, action, payload)
            return

        text = message.get("text", "").strip()
        if not text:
            return

        session_id = message.get("session_id") or "default"
        await self.chat(text, session_id=session_id, reply_to_id=msg_id)

    async def run_auto_approve(
        self,
        approval_msg_id: str,
        *,
        command: str = "",
        purpose: str = "",
        risk_level: str = "red",
        risk_source: str = "rule",
        rule_reason: str = "",
    ) -> dict[str, Any]:
        record = self._find_approval_record(approval_msg_id)
        if record:
            approval_msg_id = record["approval_msg_id"]
            command = record["command"]
            purpose = record.get("purpose") or ""
            risk_level = record.get("risk_level", risk_level)
            risk_source = record.get("risk_source", risk_source)
            rule_reason = record.get("reason") or rule_reason
        elif not command:
            return {"ok": False, "error": "not_found", "approval_id": approval_msg_id}

        approved, reason = await self.auto_approver.decide(
            command,
            purpose,
            risk_level=risk_level,
            risk_source=risk_source,
            rule_reason=rule_reason,
        )

        if not self.server:
            return {"ok": False, "error": "no_server"}

        await self.server.respond(
            approval_msg_id,
            msg_type="approval_response",
            message={"approved": approved, "reason": f"[模型自动审批] {reason}"},
        )

        pending = self._pending.get(approval_msg_id)
        if pending and not pending.future.done():
            pending.future.set_result(approved)
        else:
            self.audit.resolve_approval(
                approval_msg_id,
                status="approved" if approved else "rejected",
                reason=f"[模型自动审批] {reason}",
            )

        await self.server.send_message(
            msg_type="text",
            message={
                "text": (
                    f"模型自动审批：{'通过' if approved else '拒绝'}\n"
                    f"命令: {command}\n"
                    f"说明: {reason}"
                ),
                "role": "agent",
            },
        )

        return {"ok": True, "approved": approved, "reason": reason, "approval_id": approval_msg_id}

    async def run_auto_approve_all(self) -> dict[str, Any]:
        seen: set[str] = set()
        results: list[dict[str, Any]] = []

        for item in self.audit.list_pending_approvals():
            aid = item["approval_msg_id"]
            if not aid or aid in seen:
                continue
            seen.add(aid)
            results.append(await self.run_auto_approve(aid))

        for aid in list(self._pending.keys()):
            if not aid or aid in seen:
                continue
            seen.add(aid)
            results.append(await self.run_auto_approve(aid))

        ok_count = sum(1 for item in results if item.get("ok"))
        return {"ok": True, "processed": len(results), "succeeded": ok_count, "results": results}

    def _find_approval_record(self, approval_msg_id: str) -> dict[str, Any] | None:
        for item in self.audit.list_pending_approvals():
            if item["approval_msg_id"] == approval_msg_id:
                return item
            if item["check_id"] == approval_msg_id:
                return item
        for item in self.audit.list_approval_records(limit=100):
            if item["approval_msg_id"] == approval_msg_id or item["check_id"] == approval_msg_id:
                if item.get("status") == "pending":
                    return item
        return None

    async def chat(
        self,
        user_message: str,
        *,
        session_id: str = "default",
        reply_to_id: str | None = None,
    ) -> str:
        context = self._build_chat_context()
        history = self.audit.get_chat_messages(session_id, limit=12)
        reply = await self.assistant.chat(user_message, history, context=context)
        self.audit.append_chat(session_id, "user", user_message)
        self.audit.append_chat(session_id, "assistant", reply)

        if self.server:
            await self.server.send_message(
                msg_type="text",
                message={
                    "text": reply,
                    "role": "agent",
                    "reply_to": reply_to_id,
                },
            )
        return reply

    def _build_chat_context(self) -> str:
        pending = self.audit.list_pending_approvals()
        if pending:
            lines = ["【当前待审批】"]
            for item in pending[:3]:
                lines.append(
                    f"- check_id={item['check_id']} command={item['command']} purpose={item.get('purpose') or ''}"
                )
            return "\n".join(lines)

        yellow = self.audit.list_yellow_records(limit=security_settings.chat_context_yellow_limit)
        approvals = self.audit.list_approval_records(limit=security_settings.chat_context_approval_limit)
        lines = ["【近期黄色记录】"]
        for item in yellow:
            lines.append(f"- {item['command']} | {item.get('rule_reason')}")
        lines.append("【近期审批记录】")
        for item in approvals:
            lines.append(f"- {item['command']} | {item.get('status')}")
        return "\n".join(lines)

    async def _push_yellow_log(
        self,
        check_id: str,
        command: str,
        purpose: str,
        rule_reason: str,
        *,
        escalated: bool,
        model_reason: str,
    ) -> None:
        if not self.server:
            return
        await self.server.send_message(
            msg_type=YELLOW_LOG_MSG_TYPE,
            message={
                "text": f"黄色记录: {command}",
                "payload": {
                    "check_id": check_id,
                    "command": command,
                    "purpose": purpose,
                    "rule_reason": rule_reason,
                    "escalated": escalated,
                    "model_reason": model_reason,
                },
            },
        )
