"""主对话 FC 循环。"""

from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from modules.main.model import SYSTEM_PROMPT
from modules.main.runtime import ToolRuntime, parse_tool_arguments
from modules.main.schemas import ToolResultForModel
from modules.main.tools import tools_for_openai
from shared.llm import get_llm_client

logger = logging.getLogger(__name__)

SLOT_KEY = "main.chat"
MAX_TOOL_ROUNDS = 8
RECENT_TURNS = 6

OnText = Callable[[str], Awaitable[None]]


class PendingPlanning(Exception):
    """规划进入质询等待；FC 暂停。"""

    def __init__(self, tool_call_id: str) -> None:
        super().__init__("awaiting_clarify")
        self.tool_call_id = tool_call_id


class MainAssistant:
    def __init__(self, slot_key: str = SLOT_KEY) -> None:
        self.slot_key = slot_key

    def build_messages(
        self,
        *,
        user_text: str,
        history: list[dict[str, str]],
        manager_ctx: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        parts = [SYSTEM_PROMPT]
        if manager_ctx:
            state = manager_ctx.get("conversation_state") or {}
            summary = manager_ctx.get("conversation_summary") or ""
            open_tasks = manager_ctx.get("open_tasks") or []
            parts.append(
                "\n\n## 会话状态（由 Conversation Manager 注入）\n"
                f"State: {json.dumps(state, ensure_ascii=False)}\n"
                f"Summary: {summary or '（无）'}\n"
                f"Open Tasks: {json.dumps(open_tasks, ensure_ascii=False)}"
            )
        messages: list[dict[str, Any]] = [{"role": "system", "content": "\n".join(parts)}]
        for turn in history[-RECENT_TURNS:]:
            role = turn.get("role") or "user"
            content = turn.get("content") or ""
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_text})
        return messages

    async def run_fc_loop(
        self,
        messages: list[dict[str, Any]],
        runtime: ToolRuntime,
        *,
        available_modules: set[str] | None = None,
        on_assistant_text: OnText | None = None,
        max_rounds: int = MAX_TOOL_ROUNDS,
    ) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
        """
        返回 (final_text, tool_trace, usage_totals)。
        若规划需质询，抛出 PendingPlanning（messages 已含 assistant.tool_calls，尚无对应 tool 结果）。
        """
        llm = get_llm_client(self.slot_key)
        tools = tools_for_openai(available_modules=available_modules)
        tool_trace: list[dict[str, Any]] = []
        usage_totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        final_text = ""

        for _ in range(max_rounds):
            msg = await llm.chat_completion(
                messages,
                tools=tools or None,
                tool_choice="auto" if tools else None,
            )
            usage = msg.pop("_usage", None) or {}
            for k in usage_totals:
                usage_totals[k] += int(usage.get(k) or 0)

            tool_calls = msg.get("tool_calls") or []
            content = str(msg.get("content") or "")
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            if not tool_calls:
                final_text = content.strip()
                break

            if content.strip() and on_assistant_text:
                await on_assistant_text(content.strip())

            for tc in tool_calls:
                tc_id = str(tc.get("id") or "")
                fn = tc.get("function") or {}
                name = str(fn.get("name") or "")
                args = parse_tool_arguments(fn.get("arguments"))
                result = await runtime.invoke(name, args, request_id=tc_id)

                if result.data.get("_pending_clarify"):
                    raise PendingPlanning(tc_id)

                tool_trace.append({"tool": name, "args": args, "result": result.model_dump()})
                payload = {
                    "ok": result.ok,
                    "summary": result.summary,
                    "data": {k: v for k, v in result.data.items() if not str(k).startswith("_")},
                    "error": result.error,
                }
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps(payload, ensure_ascii=False)[:12000],
                    }
                )
        else:
            final_text = final_text or "已达到工具调用轮次上限，请根据已有结果继续，或拆分任务后再试。"

        if not final_text:
            final_text = "（无文本回复）"
        return final_text, tool_trace, usage_totals

    @staticmethod
    def inject_tool_result(
        messages: list[dict[str, Any]],
        *,
        tool_call_id: str,
        result: ToolResultForModel,
    ) -> None:
        payload = {
            "ok": result.ok,
            "summary": result.summary,
            "data": {k: v for k, v in result.data.items() if not str(k).startswith("_")},
            "error": result.error,
        }
        body = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(payload, ensure_ascii=False)[:12000],
        }
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if m.get("role") == "tool" and m.get("tool_call_id") == tool_call_id:
                messages[i] = body
                return
        messages.append(body)
