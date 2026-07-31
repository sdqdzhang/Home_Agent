"""规划黑盒：自然语言任务 → clarify/env_probe/plan/run_graph；UI 用单卡 planning_session 原地更新。"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal

from modules.planning import MAX_COLLECT_ROUNDS
from modules.planning.schemas import (
    ClarifyAnswer,
    ClarifyOutcome,
    ClarifyQuestion,
    ClarifyRequest,
    EnvProbeRecord,
    PlanRequest,
    compose_goal,
)
from modules.processor.schemas import DataBlock
from modules.main.schemas import ToolResultForModel
from shared.local_bus import call

logger = logging.getLogger(__name__)

# push(msg_type, message, msg_id=None) -> message_id
PushFn = Callable[..., Awaitable[str]]
# update(msg_id, message) -> None
UpdateFn = Callable[[str, dict[str, Any]], Awaitable[None]]
BridgeStatus = Literal["running", "awaiting_clarify", "done", "cancelled"]
Phase = Literal[
    "collecting",
    "clarifying",
    "probing",
    "planning",
    "running",
    "done",
    "failed",
    "cancelled",
]


@dataclass
class PlanningBridgeState:
    task: str
    request_id: str = ""
    tool_call_id: str = ""
    session_id: str = "default"
    status: BridgeStatus = "running"
    round_index: int = 1
    history: list[ClarifyAnswer] = field(default_factory=list)
    env_records: list[EnvProbeRecord] = field(default_factory=list)
    env_blocks: list[DataBlock] = field(default_factory=list)
    pending_questions: list[ClarifyQuestion] = field(default_factory=list)
    session_msg_id: str = ""
    cancelled: bool = False
    final_result: ToolResultForModel | None = None
    # 可变会话卡快照（patch 用）
    card: dict[str, Any] = field(default_factory=dict)


class PlanningBridge:
    """由 main 持有；中间过程只更新 planning_session 卡，最终结果回灌主模型。"""

    def __init__(self, *, push: PushFn, update: UpdateFn | None = None) -> None:
        self.push = push
        self.update = update

    def request_cancel(self, state: PlanningBridgeState) -> None:
        state.cancelled = True

    def _cancelled(self, state: PlanningBridgeState) -> bool:
        return bool(state.cancelled)

    async def _sync_card(self, state: PlanningBridgeState, **patch: Any) -> None:
        state.card.update(patch)
        state.card.setdefault("request_id", state.request_id)
        state.card.setdefault("session_id", state.session_id)
        state.card.setdefault("goal", state.task)
        state.card["can_cancel"] = state.card.get("phase") not in (
            "done",
            "failed",
            "cancelled",
        )
        if not state.session_msg_id:
            return
        if not self.update:
            return
        try:
            await self.update(state.session_msg_id, dict(state.card))
        except Exception:
            logger.exception("planning_session update failed")

    async def start(
        self,
        task: str,
        *,
        request_id: str = "",
        tool_call_id: str = "",
        session_id: str = "default",
        on_state: Callable[[PlanningBridgeState], None] | None = None,
    ) -> PlanningBridgeState:
        rid = request_id or f"plan_{uuid.uuid4().hex[:12]}"
        state = PlanningBridgeState(
            task=task.strip(),
            request_id=rid,
            tool_call_id=tool_call_id or rid,
            session_id=session_id or "default",
        )
        state.card = {
            "ok": True,
            "request_id": rid,
            "session_id": state.session_id,
            "goal": state.task,
            "summary": "",
            "status": "collecting",
            "phase": "collecting",
            "graph": None,
            "node_status": {},
            "questions": [],
            "error": "",
            "files": [],
            "can_cancel": True,
            "text": "已开始规划，正在收集信息…",
        }
        msg_id = f"main_plan_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        state.session_msg_id = await self.push(
            "planning_session",
            dict(state.card),
            msg_id=msg_id,
        )
        if on_state is not None:
            on_state(state)
        return await self._advance(state)

    async def provide_clarify_answers(
        self,
        state: PlanningBridgeState,
        user_text: str = "",
        *,
        answers: list[ClarifyAnswer] | None = None,
    ) -> PlanningBridgeState:
        if self._cancelled(state):
            return await self._cancel(state)

        resolved: list[ClarifyAnswer] = []
        if answers:
            by_id = {a.question_id: a for a in answers if (a.answer or "").strip()}
            for q in state.pending_questions:
                hit = by_id.get(q.id)
                if hit is not None:
                    resolved.append(
                        ClarifyAnswer(
                            question_id=q.id,
                            answer=hit.answer.strip(),
                            question=hit.question or q.prompt,
                        )
                    )
            if not resolved:
                resolved = [a for a in answers if (a.answer or "").strip()]
        else:
            text = (user_text or "").strip()
            if not text:
                return state
            resolved = [
                ClarifyAnswer(question_id=q.id, answer=text, question=q.prompt)
                for q in state.pending_questions
            ]
            if not resolved:
                resolved = [ClarifyAnswer(question_id="user", answer=text, question="用户补充")]

        if not resolved:
            return state

        state.history.extend(resolved)
        state.pending_questions = []
        state.status = "running"
        state.round_index += 1
        await self._sync_card(
            state,
            phase="collecting",
            status="collecting",
            questions=[],
            text="已收到补充信息，继续规划…",
        )
        return await self._advance(state)

    async def _advance(self, state: PlanningBridgeState) -> PlanningBridgeState:
        while True:
            if self._cancelled(state):
                return await self._cancel(state)
            if state.round_index > MAX_COLLECT_ROUNDS:
                return await self._fail(state, f"信息收集超过 {MAX_COLLECT_ROUNDS} 轮")

            try:
                outcome: ClarifyOutcome = await call(
                    "planning",
                    "clarify",
                    ClarifyRequest(
                        goal=state.task,
                        history=list(state.history),
                        env_records=list(state.env_records),
                        round_index=state.round_index,
                    ),
                )
            except Exception as exc:
                logger.exception("planning.clarify failed")
                return await self._fail(state, f"质询失败: {exc}")

            if self._cancelled(state):
                return await self._cancel(state)

            if outcome.env_queries:
                await self._sync_card(
                    state,
                    phase="probing",
                    status="probing",
                    text=f"环境探测 {len(outcome.env_queries)} 项…",
                    questions=[],
                )
                await self._run_env_probes(state, outcome)
                if self._cancelled(state):
                    return await self._cancel(state)

            if outcome.ready:
                return await self._plan_and_run(state)

            if outcome.questions:
                state.pending_questions = list(outcome.questions)
                state.status = "awaiting_clarify"
                await self._sync_card(
                    state,
                    phase="clarifying",
                    status="clarifying",
                    questions=[q.model_dump() for q in outcome.questions],
                    round_index=state.round_index,
                    text=f"规划需要补充信息（{len(outcome.questions)} 题）",
                )
                return state

            # 仅 env_probe 的一轮：继续下一轮 clarify
            state.round_index += 1

    async def _run_env_probes(self, state: PlanningBridgeState, outcome: ClarifyOutcome) -> None:
        for q in outcome.env_queries:
            if self._cancelled(state):
                return
            block_id = f"env_{q.id}"
            try:
                rec, blk = await call(
                    "planning",
                    "run_env_query",
                    q,
                    block_id=block_id,
                    round_index=state.round_index,
                )
            except Exception as exc:
                logger.exception("env probe failed %s", q.id)
                from modules.planning.schemas import EnvProbeRecord

                rec = EnvProbeRecord(
                    id=q.id,
                    instruction=q.instruction,
                    purpose=q.purpose,
                    status="failed",
                    summary=str(exc),
                    round_index=state.round_index,
                )
                blk = None
            state.env_records.append(rec)
            if blk is not None:
                state.env_blocks.append(blk)

        await self._sync_card(
            state,
            text=f"已完成 {len(outcome.env_queries)} 项环境探测",
        )

    async def _plan_and_run(self, state: PlanningBridgeState) -> PlanningBridgeState:
        if self._cancelled(state):
            return await self._cancel(state)

        effective_goal = compose_goal(state.task, state.history)
        await self._sync_card(
            state,
            phase="planning",
            status="planning",
            goal=effective_goal,
            questions=[],
            text="正在生成任务图…",
        )
        try:
            plan_out = await call(
                "planning",
                "plan",
                PlanRequest(
                    goal=effective_goal,
                    clarifications=list(state.history),
                    context_blocks=list(state.env_blocks),
                ),
            )
        except Exception as exc:
            logger.exception("planning.plan failed")
            return await self._fail(state, f"出图失败: {exc}")

        if self._cancelled(state):
            return await self._cancel(state)

        if not plan_out.ok or plan_out.graph is None:
            return await self._fail(state, plan_out.error or "出图失败")

        graph = plan_out.graph
        node_status: dict[str, dict[str, Any]] = {
            n.id: {"status": "pending", "attempts": 0, "error": "", "detail": ""}
            for n in graph.nodes
        }
        await self._sync_card(
            state,
            ok=True,
            goal=effective_goal,
            summary=graph.summary,
            status="running",
            phase="running",
            graph=graph.model_dump(by_alias=True),
            node_status=node_status,
            error="",
            text=f"任务图已生成：{graph.summary or '（无摘要）'}",
        )

        def on_progress(node_id: str, status: str, attempts: int, detail: str) -> None:
            import asyncio

            node_status[node_id] = {
                "status": status,
                "attempts": attempts,
                "error": detail if status == "failed" else "",
                "detail": detail or "",
            }
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return

            async def _patch() -> None:
                if self._cancelled(state):
                    return
                await self._sync_card(
                    state,
                    node_status=dict(node_status),
                    text=f"{node_id} → {status}",
                )

            loop.create_task(_patch())

        try:
            run = await call(
                "planning",
                "run_graph",
                effective_goal,
                graph,
                initial_blocks=list(state.env_blocks),
                on_progress=on_progress,
                cancel_check=lambda: self._cancelled(state),
            )
        except Exception as exc:
            logger.exception("run_graph failed")
            return await self._fail(state, f"执行图失败: {exc}")

        if self._cancelled(state) or (run.error or "").startswith("用户取消"):
            # 合并最终节点状态后标取消
            for n in run.nodes or []:
                raw = n.model_dump() if hasattr(n, "model_dump") else dict(n)
                nid = str(raw.get("node_id") or "")
                if nid:
                    node_status[nid] = {
                        "status": raw.get("status") or "skipped",
                        "attempts": int(raw.get("attempts") or 0),
                        "error": raw.get("error") or "",
                        "detail": "",
                    }
            return await self._cancel(state, node_status=node_status, graph=graph, goal=effective_goal)

        files: list[str] = []
        for b in run.blocks or []:
            if isinstance(b, dict):
                meta = b.get("metadata") or {}
                path = meta.get("path") if isinstance(meta, dict) else None
                if path:
                    files.append(str(path))
                for p in (meta.get("files_touched") if isinstance(meta, dict) else None) or []:
                    files.append(str(p))

        for n in run.nodes or []:
            raw = n.model_dump() if hasattr(n, "model_dump") else dict(n)
            nid = str(raw.get("node_id") or "")
            if not nid:
                continue
            node_status[nid] = {
                "status": raw.get("status") or ("succeeded" if run.ok else "failed"),
                "attempts": int(raw.get("attempts") or 0),
                "error": raw.get("error") or "",
                "detail": "",
            }
        for nid in run.skipped_node_ids or []:
            node_status.setdefault(
                str(nid),
                {"status": "skipped", "attempts": 0, "error": "", "detail": ""},
            )

        data = {
            "ok": run.ok,
            "goal": run.goal,
            "summary": run.summary,
            "error": run.error,
            "files": list(dict.fromkeys(files)),
            "nodes": [n.model_dump() if hasattr(n, "model_dump") else n for n in (run.nodes or [])],
            "skipped_node_ids": list(run.skipped_node_ids or []),
        }
        final_text = ("规划执行成功" if run.ok else f"规划执行失败: {run.error}") + (
            f"；产出文件 {len(data['files'])} 个" if data["files"] else ""
        )
        await self._sync_card(
            state,
            ok=bool(run.ok),
            goal=effective_goal,
            summary=run.summary or graph.summary,
            status="succeeded" if run.ok else "failed",
            phase="done" if run.ok else "failed",
            graph=graph.model_dump(by_alias=True),
            node_status=node_status,
            error="" if run.ok else (run.error or "执行失败"),
            files=data["files"],
            questions=[],
            text=final_text,
            can_cancel=False,
        )
        state.status = "done"
        state.final_result = ToolResultForModel(
            ok=bool(run.ok),
            tool="planning_run",
            summary=run.summary or ("成功" if run.ok else run.error or "失败"),
            data=data,
            error="" if run.ok else (run.error or "graph run failed"),
        )
        return state

    async def _cancel(
        self,
        state: PlanningBridgeState,
        *,
        node_status: dict[str, dict[str, Any]] | None = None,
        graph: Any = None,
        goal: str = "",
    ) -> PlanningBridgeState:
        state.cancelled = True
        state.status = "cancelled"
        err = "用户取消规划"
        await self._sync_card(
            state,
            ok=False,
            goal=goal or state.task,
            status="cancelled",
            phase="cancelled",
            node_status=node_status or state.card.get("node_status") or {},
            graph=graph.model_dump(by_alias=True) if graph is not None else state.card.get("graph"),
            error=err,
            questions=[],
            text=err,
            can_cancel=False,
        )
        state.final_result = ToolResultForModel(
            ok=False,
            tool="planning_run",
            summary=err,
            data={"ok": False, "goal": state.task, "files": [], "error": err, "cancelled": True},
            error=err,
        )
        return state

    async def _fail(self, state: PlanningBridgeState, error: str) -> PlanningBridgeState:
        state.status = "done"
        state.final_result = ToolResultForModel(
            ok=False,
            tool="planning_run",
            summary=error,
            data={"ok": False, "goal": state.task, "files": [], "error": error},
            error=error,
        )
        await self._sync_card(
            state,
            ok=False,
            status="failed",
            phase="failed",
            error=error,
            questions=[],
            text=f"规划结束（失败）：{error}",
            can_cancel=False,
        )
        return state
