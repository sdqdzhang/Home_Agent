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


def _trim_tool_data(data: dict[str, Any]) -> dict[str, Any]:
    out = {
        k: v
        for k, v in data.items()
        if not str(k).startswith("_") and k not in ("parsed_action",)
    }
    if isinstance(out.get("stdout"), str):
        out["stdout"] = out["stdout"][:1500]
    if isinstance(out.get("stderr"), str):
        out["stderr"] = out["stderr"][:500]
    if isinstance(out.get("content"), str):
        out["content"] = out["content"][:3000]
    return out


class MainAssistant:
    def __init__(self, slot_key: str = SLOT_KEY) -> None:
        self.slot_key = slot_key

    def build_messages(
        self,
        *,
        user_text: str,
        history: list[dict[str, str]],
        manager_ctx: dict[str, Any] | None,
        mind_ctx: dict[str, Any] | None = None,
        memory_ctx: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        parts = [SYSTEM_PROMPT]
        mind_text = ""
        if mind_ctx:
            mind_text = str(mind_ctx.get("mind_context") or "").strip()
        if mind_text:
            parts.append("\n\n" + mind_text)

        if manager_ctx:
            state = manager_ctx.get("conversation_state") or {}
            summary = manager_ctx.get("conversation_summary") or ""
            open_tasks = manager_ctx.get("open_tasks") or []
            parts.append(
                "\n\n## 会话状态（Conversation State — 当前结构化事实）\n"
                f"{json.dumps(state, ensure_ascii=False)}"
            )
            parts.append(
                "\n\n## 会话摘要（Summary — 更早对话的滚动压缩，不是 State）\n"
                f"{summary or '（无）'}"
            )
            parts.append(
                "\n\n## Open Tasks（仅供参考；是否继续由你根据用户当前话决定，不要自动开跑）\n"
                f"{json.dumps(open_tasks, ensure_ascii=False)}"
            )

        memory_text = ""
        if memory_ctx:
            memory_text = str(memory_ctx.get("text") or "").strip()
        if memory_text:
            parts.append(
                "\n\n## 长期记忆（可选参考）\n"
                "以下是系统检索到的用户相关记忆。规则：\n"
                "- 与当前问题相关才使用；\n"
                "- 无关则忽略，不要主动提起，也不要硬往记忆话题上靠；\n"
                "- 不要把记忆当成必须完成的任务列表。\n\n"
                f"{memory_text}"
            )

        messages: list[dict[str, Any]] = [{"role": "system", "content": "\n".join(parts)}]
        for turn in history[-RECENT_TURNS:]:
            role = turn.get("role") or "user"
            content = turn.get("content") or ""
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": user_text})
        return messages

    async def _ask_text_reply(
        self,
        llm: Any,
        messages: list[dict[str, Any]],
        usage_totals: dict[str, int],
        *,
        nudge: bool = False,
    ) -> str:
        """工具执行后强制要一轮纯文本（不带 tools），避免模型空 content 结束。"""
        if nudge:
            messages.append(
                {
                    "role": "user",
                    "content": "请根据刚才的工具结果，用一两句中文向用户说明完成情况。不要调用工具。",
                }
            )
        msg = await llm.chat_completion(messages, tools=None, tool_choice=None)
        usage = msg.pop("_usage", None) or {}
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if k in usage_totals:
                usage_totals[k] += int(usage.get(k) or 0)
        prompt_n = int(usage.get("prompt_tokens") or 0)
        if prompt_n > int(usage_totals.get("max_prompt_tokens") or 0):
            usage_totals["max_prompt_tokens"] = prompt_n
        # 即便模型仍返回 tool_calls，也忽略，只取文本
        text = str(msg.get("content") or "").strip()
        messages.append({"role": "assistant", "content": text})
        return text

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

        工具回合结束后立刻再请求一轮「禁止工具」的文本回复，再决定是否进入下一轮工具。
        """
        llm = get_llm_client(self.slot_key)
        tools = tools_for_openai(available_modules=available_modules)
        tool_trace: list[dict[str, Any]] = []
        usage_totals = {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "max_prompt_tokens": 0,
        }
        final_text = ""

        for _ in range(max_rounds):
            msg = await llm.chat_completion(
                messages,
                tools=tools or None,
                tool_choice="auto" if tools else None,
            )
            usage = msg.pop("_usage", None) or {}
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                usage_totals[k] += int(usage.get(k) or 0)
            prompt_n = int(usage.get("prompt_tokens") or 0)
            if prompt_n > usage_totals["max_prompt_tokens"]:
                usage_totals["max_prompt_tokens"] = prompt_n

            tool_calls = msg.get("tool_calls") or []
            content = str(msg.get("content") or "").strip()

            if not tool_calls:
                messages.append({"role": "assistant", "content": content})
                final_text = content
                break

            if content and on_assistant_text:
                await on_assistant_text(content)

            # 带 tool_calls 时 content 常为空；用空字符串即可，避免部分网关拒绝 null
            messages.append(
                {
                    "role": "assistant",
                    "content": content or "",
                    "tool_calls": tool_calls,
                }
            )

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
                    "data": _trim_tool_data(result.data),
                    "error": result.error,
                }
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc_id,
                        "content": json.dumps(payload, ensure_ascii=False)[:8000],
                    }
                )

            # 本轮工具已完成 → 强制纯文本说明（不再挂 tools，避免空回复）
            try:
                text = await self._ask_text_reply(llm, messages, usage_totals, nudge=False)
                if not text:
                    text = await self._ask_text_reply(llm, messages, usage_totals, nudge=True)
            except Exception:
                logger.exception("text reply after tools failed")
                text = ""

            if text:
                final_text = text
                break

            # 仍无文本：允许下一轮再决策（少数多工具场景）；最后一轮则结束
            logger.warning("model returned empty text after tools; continuing fc loop")
        else:
            final_text = final_text or "已达到工具调用轮次上限，请根据上方结果继续，或拆分任务后再试。"

        if not final_text:
            # 仍空：至少让用户知道流程结束（非工具摘要拼装）
            final_text = "好的，我这边处理好了。还需要做什么可以直接说。"
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
            "data": _trim_tool_data(result.data),
            "error": result.error,
        }
        body = {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(payload, ensure_ascii=False)[:8000],
        }
        for i in range(len(messages) - 1, -1, -1):
            m = messages[i]
            if m.get("role") == "tool" and m.get("tool_call_id") == tool_call_id:
                messages[i] = body
                return
        messages.append(body)
