"""规划黑盒：自然语言任务 → clarify/env_probe/plan/run_graph；质询等人机交互进主对话时间线。"""

from __future__ import annotations

import logging
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

PushFn = Callable[[str, dict[str, Any]], Awaitable[None]]
BridgeStatus = Literal["running", "awaiting_clarify", "done"]


@dataclass
class PlanningBridgeState:
    task: str
    request_id: str = ""
    tool_call_id: str = ""
    status: BridgeStatus = "running"
    round_index: int = 1
    history: list[ClarifyAnswer] = field(default_factory=list)
    env_records: list[EnvProbeRecord] = field(default_factory=list)
    env_blocks: list[DataBlock] = field(default_factory=list)
    pending_questions: list[ClarifyQuestion] = field(default_factory=list)
    final_result: ToolResultForModel | None = None


class PlanningBridge:
    """由 main 持有；不把中间过程回灌主模型，只在结束时给出结构化结果。"""

    def __init__(self, *, push: PushFn) -> None:
        self.push = push

    async def start(self, task: str, *, request_id: str = "", tool_call_id: str = "") -> PlanningBridgeState:
        state = PlanningBridgeState(task=task.strip(), request_id=request_id, tool_call_id=tool_call_id)
        await self.push(
            "text",
            {
                "text": f"已开始规划任务（程序接管，主模型等待最终结果）：\n{state.task}",
                "role": "agent",
                "request_id": request_id,
            },
        )
        return await self._advance(state)

    async def provide_clarify_answers(self, state: PlanningBridgeState, user_text: str) -> PlanningBridgeState:
        text = (user_text or "").strip()
        if not text:
            await self.push("text", {"text": "请回答上方质询后再继续。", "role": "agent"})
            return state
        answers = [
            ClarifyAnswer(question_id=q.id, answer=text, question=q.prompt)
            for q in state.pending_questions
        ]
        if not answers:
            answers = [ClarifyAnswer(question_id="user", answer=text, question="用户补充")]
        state.history.extend(answers)
        state.pending_questions = []
        state.status = "running"
        state.round_index += 1
        return await self._advance(state)

    async def _advance(self, state: PlanningBridgeState) -> PlanningBridgeState:
        while True:
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

            body = outcome.model_dump()
            body["request_id"] = state.request_id
            body["goal"] = state.task
            body["round_index"] = state.round_index
            if outcome.ready:
                body["text"] = outcome.note or "信息已足够，准备出图"
            elif outcome.questions:
                body["text"] = f"质询 {len(outcome.questions)} 题" + (f"；探测 {len(outcome.env_queries)} 项" if outcome.env_queries else "")
            else:
                body["text"] = f"环境探测 {len(outcome.env_queries)} 项"
            await self.push("clarify_result", body)

            if outcome.env_queries:
                await self._run_env_probes(state, outcome)

            if outcome.ready:
                return await self._plan_and_run(state)

            if outcome.questions:
                state.pending_questions = list(outcome.questions)
                state.status = "awaiting_clarify"
                lines = ["规划需要补充信息（请直接回复；回复将作为本轮质询答案）：", ""]
                for i, q in enumerate(outcome.questions, 1):
                    choices = " / ".join(q.choices[:6])
                    lines.append(f"{i}. {q.prompt}")
                    if choices:
                        lines.append(f"   选项：{choices}（也可自由回答）")
                    if q.reason:
                        lines.append(f"   原因：{q.reason}")
                await self.push("text", {"text": "\n".join(lines), "role": "agent", "request_id": state.request_id})
                return state

            # 仅 env_probe 的一轮：继续下一轮 clarify
            state.round_index += 1

    async def _run_env_probes(self, state: PlanningBridgeState, outcome: ClarifyOutcome) -> None:
        results: list[dict[str, Any]] = []
        for q in outcome.env_queries:
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
            results.append(
                {
                    "record": rec.model_dump(),
                    "block": blk.model_dump() if blk is not None else None,
                }
            )
        await self.push(
            "env_probe_result",
            {
                "request_id": state.request_id,
                "round_index": state.round_index,
                "results": results,
                "text": f"已完成 {len(results)} 项环境探测",
            },
        )

    async def _plan_and_run(self, state: PlanningBridgeState) -> PlanningBridgeState:
        effective_goal = compose_goal(state.task, state.history)
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

        if not plan_out.ok or plan_out.graph is None:
            await self.push(
                "plan_result",
                {
                    "ok": False,
                    "request_id": state.request_id,
                    "goal": effective_goal,
                    "summary": "",
                    "status": "failed",
                    "graph": None,
                    "error": plan_out.error or "出图失败",
                    "text": plan_out.error or "出图失败",
                },
            )
            return await self._fail(state, plan_out.error or "出图失败")

        graph = plan_out.graph
        await self.push(
            "plan_result",
            {
                "ok": True,
                "request_id": state.request_id,
                "goal": effective_goal,
                "summary": graph.summary,
                "status": "running",
                "graph": graph.model_dump(by_alias=True),
                "error": "",
                "text": f"任务图已生成：{graph.summary or '（无摘要）'}，开始执行…",
            },
        )

        def on_progress(node_id: str, status: str, attempts: int, detail: str) -> None:
            # sync callback — schedule best-effort via create_task from caller loop
            import asyncio

            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                return

            async def _push() -> None:
                await self.push(
                    "plan_progress",
                    {
                        "request_id": state.request_id,
                        "node_id": node_id,
                        "status": status,
                        "attempts": attempts,
                        "detail": detail,
                        "text": f"[{status}] {node_id}: {detail}",
                    },
                )

            loop.create_task(_push())

        try:
            run = await call(
                "planning",
                "run_graph",
                effective_goal,
                graph,
                initial_blocks=list(state.env_blocks),
                on_progress=on_progress,
            )
        except Exception as exc:
            logger.exception("run_graph failed")
            return await self._fail(state, f"执行图失败: {exc}")

        files: list[str] = []
        for b in run.blocks or []:
            if isinstance(b, dict):
                meta = b.get("metadata") or {}
                path = meta.get("path") if isinstance(meta, dict) else None
                if path:
                    files.append(str(path))
                for p in (meta.get("files_touched") if isinstance(meta, dict) else None) or []:
                    files.append(str(p))

        data = {
            "ok": run.ok,
            "goal": run.goal,
            "summary": run.summary,
            "error": run.error,
            "files": list(dict.fromkeys(files)),
            "nodes": [n.model_dump() if hasattr(n, "model_dump") else n for n in (run.nodes or [])],
            "skipped_node_ids": list(run.skipped_node_ids or []),
        }
        await self.push(
            "graph_run_result",
            {
                **data,
                "request_id": state.request_id,
                "text": ("规划执行成功" if run.ok else f"规划执行失败: {run.error}")
                + (f"；产出文件 {len(data['files'])} 个" if data["files"] else ""),
            },
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

    async def _fail(self, state: PlanningBridgeState, error: str) -> PlanningBridgeState:
        state.status = "done"
        state.final_result = ToolResultForModel(
            ok=False,
            tool="planning_run",
            summary=error,
            data={"ok": False, "goal": state.task, "files": [], "error": error},
            error=error,
        )
        await self.push(
            "text",
            {"text": f"规划结束（失败）：{error}", "role": "agent", "request_id": state.request_id},
        )
        return state
