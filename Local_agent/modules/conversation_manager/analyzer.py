"""Conversation Analyzer：规则命中后用 LLM 更新 State / 候选记忆等。"""

from __future__ import annotations

import logging
from typing import Any

from modules.conversation_manager.schemas import (
    AnalyzerMode,
    AnalyzerOutput,
    ConversationState,
    MemoryCandidate,
    OpenTask,
    TurnEndEvent,
)
from shared.llm import get_llm_client

logger = logging.getLogger(__name__)

SLOT_KEY = "conversation.analyze"

LIGHT_SYSTEM = """你是会话状态分析器。根据「上一轮 Conversation State + 本轮用户与助手发言」，输出更新后的 JSON：
{
  "conversation_state": {
    "current_project": "",
    "current_topic": "",
    "task_progress": "",
    "active_tasks": [],
    "preferences": [],
    "notes": ""
  },
  "memory_candidates": [{"content": "一句可入库的长期记忆候选", "tags": []}],
  "open_tasks": [{"id": "", "title": "", "detail": "", "status": "open", "origin": "", "context": ""}],
  "important_files": ["path"]
}
规则：
- 保留仍有效的旧状态；仅在有依据时更新。
- memory_candidates **极严**：只放用户明确的长期偏好、技术栈选型、安全/权限规则、对未来行为有约束的决策。
- **禁止**把一次性工具结果、env 监控采样、CPU/内存占用、瞬时进程状态、单次成功/失败写入 memory_candidates。
- 没有真正值得长期记住的内容时，memory_candidates 必须为 []。
- Open Tasks 只记录未完成工作，并尽量填写 origin（来源简述）与 context（恢复所需最短上下文）；不要暗示自动执行。
只返回 JSON。"""

FULL_SYSTEM = """你是会话压缩与分析器。在上下文将尽时，一次输出：
{
  "conversation_summary": "供新上下文初始化的摘要（增量滚动：结合旧 Summary 与本轮要点，不要复述瞬时监控数字）",
  "conversation_state": {
    "current_project": "",
    "current_topic": "",
    "task_progress": "",
    "active_tasks": [],
    "preferences": [],
    "notes": ""
  },
  "memory_candidates": [{"content": "...", "tags": []}],
  "open_tasks": [{"id": "", "title": "", "detail": "", "status": "open", "origin": "", "context": ""}],
  "important_files": ["path"]
}
Open Tasks 只记录未完成工作，并尽量带 origin/context；不要暗示自动执行。
memory_candidates 规则同 light：只放长期偏好/决策/铁律；禁止监控采样与一次性工具流水账。无则 []。
只返回 JSON。"""



class ConversationAnalyzer:
    def __init__(self, slot_key: str = SLOT_KEY) -> None:
        self.slot_key = slot_key

    async def run(
        self,
        *,
        mode: AnalyzerMode,
        prev_state: ConversationState,
        event: TurnEndEvent,
        prev_summary: str = "",
        prev_open_tasks: list[OpenTask] | None = None,
    ) -> AnalyzerOutput:
        if mode == "none":
            return AnalyzerOutput(
                mode="none",
                conversation_state=prev_state,
                conversation_summary=prev_summary,
                open_tasks=list(prev_open_tasks or []),
            )

        try:
            data = await self._call_llm(mode, prev_state, event, prev_summary, prev_open_tasks or [])
        except Exception as exc:
            logger.exception("Analyzer LLM failed")
            return self._fallback(mode, prev_state, event, prev_summary, prev_open_tasks or [], note=str(exc))

        return self._parse(mode, data, prev_state, prev_summary, prev_open_tasks or [], event)

    async def _call_llm(
        self,
        mode: AnalyzerMode,
        prev_state: ConversationState,
        event: TurnEndEvent,
        prev_summary: str,
        open_tasks: list[OpenTask],
    ) -> dict[str, Any]:
        llm = get_llm_client(self.slot_key)
        system = FULL_SYSTEM if mode == "full" else LIGHT_SYSTEM
        user = {
            "mode": mode,
            "previous_state": prev_state.model_dump(),
            "previous_summary": prev_summary,
            "previous_open_tasks": [t.model_dump() for t in open_tasks],
            "user_text": event.user_text,
            "assistant_text": event.assistant_text,
            "tool_calls": event.tool_calls[:10],
            "files_changed": event.files_changed[:20],
            "project_hint": event.project_hint,
        }
        import json

        return await llm.chat_json(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ]
        )

    def _parse(
        self,
        mode: AnalyzerMode,
        data: dict[str, Any],
        prev_state: ConversationState,
        prev_summary: str,
        prev_open_tasks: list[OpenTask],
        event: TurnEndEvent,
    ) -> AnalyzerOutput:
        raw_state = data.get("conversation_state") if isinstance(data, dict) else None
        try:
            state = (
                ConversationState.model_validate(raw_state)
                if isinstance(raw_state, dict)
                else prev_state.model_copy(deep=True)
            )
        except Exception:
            state = prev_state.model_copy(deep=True)

        summary = prev_summary
        if mode == "full":
            summary = str(data.get("conversation_summary") or prev_summary or "").strip() or prev_summary

        candidates: list[MemoryCandidate] = []
        for item in data.get("memory_candidates") or []:
            if isinstance(item, dict) and str(item.get("content") or "").strip():
                candidates.append(
                    MemoryCandidate(
                        content=str(item.get("content") or "").strip(),
                        tags=[str(t) for t in (item.get("tags") or []) if str(t).strip()],
                    )
                )

        open_tasks: list[OpenTask] = []
        for item in data.get("open_tasks") or []:
            if isinstance(item, dict) and (item.get("title") or item.get("detail") or item.get("id")):
                task = OpenTask.model_validate(item)
                if not task.created_turn:
                    task.created_turn = event.turn_index
                task.last_updated_turn = event.turn_index
                open_tasks.append(task)
        if not open_tasks:
            open_tasks = list(prev_open_tasks)

        files = [str(x) for x in (data.get("important_files") or []) if str(x).strip()]

        return AnalyzerOutput(
            mode=mode,
            conversation_state=state,
            conversation_summary=summary,
            memory_candidates=candidates,
            open_tasks=open_tasks,
            important_files=files,
            note="ok",
        )

    def _fallback(
        self,
        mode: AnalyzerMode,
        prev_state: ConversationState,
        event: TurnEndEvent,
        prev_summary: str,
        open_tasks: list[OpenTask],
        *,
        note: str,
    ) -> AnalyzerOutput:
        state = prev_state.model_copy(deep=True)
        if event.project_hint and not state.current_project:
            state.current_project = event.project_hint.strip()
        if event.user_text:
            state.current_topic = event.user_text.strip()[:80]
        summary = prev_summary
        if mode == "full" and not summary:
            summary = f"session={event.session_id} turn={event.turn_index}（fallback）"
        return AnalyzerOutput(
            mode=mode,
            conversation_state=state,
            conversation_summary=summary,
            open_tasks=list(open_tasks),
            note=f"fallback: {note}",
        )
