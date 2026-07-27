"""规划服务：信息收集（质询 + 环境探测）→ 出图 →（可选）拓扑执行。

主对话 / UI 编排职责见 INTEGRATION.md；本服务提供原子能力 + UI 消息入口。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from shared.server_center.client import ServerCenterClient
from modules.executor.schemas import ExecuteRequest, ExecuteResult
from modules.planning import (
    ENV_BLOCK_TYPE,
    MODULE_ALIASES,
    MODULE_ID,
    MODULE_NAME,
)
from modules.planning.model import PlanningAssistant
from modules.planning.runtime import GraphRuntime
from modules.planning.schemas import (
    ClarifyOutcome,
    ClarifyQuestion,
    ClarifyRequest,
    EnvProbeRecord,
    EnvQuery,
    GraphRunResult,
    PlanOutcome,
    PlanRequest,
    TaskGraph,
    compose_goal,
)
from modules.planning.validate import validate_task_graph
from modules.processor.schemas import DataBlock
from shared.local_bus import call

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]

# 环境探测只允许只读；若执行模块路由到这些改动型能力则拦截
_MUTATING_ACTION_TYPES = frozenset({"file.write", "file.delete"})

# UI → Local
UI_MSG_TYPES = frozenset({"text", "planning_request"})
# Local → UI
MSG_CLARIFY_RESULT = "clarify_result"
MSG_ENV_PROBE_RESULT = "env_probe_result"
MSG_PLAN_RESULT = "plan_result"
MSG_PLAN_PROGRESS = "plan_progress"
MSG_GRAPH_RUN_RESULT = "graph_run_result"


def _summarize(text: str, limit: int = 400) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit] + f"…(+{len(text) - limit})"


class PlanningService:
    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        self.server = server_client
        self.assistant = PlanningAssistant()

    async def clarify(self, req: ClarifyRequest) -> ClarifyOutcome:
        outcome, err = await self.assistant.clarify(
            req.goal,
            list(req.history),
            list(req.env_records),
            req.round_index,
        )
        if err or outcome is None:
            return ClarifyOutcome(
                ready=False,
                note=err or "信息收集失败",
                questions=[
                    ClarifyQuestion(
                        id="fallback_goal",
                        prompt="信息收集模型失败。请确认目标是否已足够明确，或补充关键约束：",
                        reason=err or "clarify error",
                        choices=["目标已足够明确，直接规划", "我再补充说明（请在下一题自由描述）"],
                    )
                ],
            )
        return outcome

    async def run_env_query(
        self,
        query: EnvQuery,
        *,
        block_id: str,
        round_index: int = 1,
    ) -> tuple[EnvProbeRecord, DataBlock | None]:
        """执行一条环境探测（经 Executor→Security）。

        成功且为只读 → 返回 (record, DataBlock)；失败/被拒/非只读 → (record, None)。
        用户拒绝的探测不应调用本方法（由编排层直接标记 denied_user）。
        """

        def _record(status: str, summary: str, bid: str = "") -> EnvProbeRecord:
            return EnvProbeRecord(
                id=query.id,
                instruction=query.instruction,
                purpose=query.purpose,
                status=status,  # type: ignore[arg-type]
                block_id=bid,
                summary=_summarize(summary),
                round_index=round_index,
            )

        req = ExecuteRequest(
            action_text=query.instruction,
            mode=None,
            caller_module=MODULE_ID,
            caller_request_id=query.id,
            purpose=query.purpose or "environment probe",
        )
        try:
            result: ExecuteResult = await call("executor", "execute", req)
        except Exception as exc:
            logger.exception("env probe %s crashed", query.id)
            return _record("failed", f"执行异常: {exc}"), None

        action_type = result.action_type or ""
        if not result.ok:
            if (result.error or "") == "security_denied":
                return _record("denied_security", result.reason or "安全拒绝"), None
            return _record("failed", result.reason or result.error or "执行失败"), None

        if action_type in _MUTATING_ACTION_TYPES:
            return _record("denied_security", f"非只读操作被拒（{action_type}）"), None

        content = result.stdout or ""
        block = DataBlock(
            id=block_id,
            type=ENV_BLOCK_TYPE,
            content=content,
            producer="planning:env",
            metadata={
                "instruction": query.instruction,
                "purpose": query.purpose,
                "action_type": action_type,
                "path": (result.files_touched or [""])[0] if result.files_touched else "",
                "files_touched": list(result.files_touched or []),
                "exit_code": result.exit_code,
                "job_id": result.job_id,
                "round": round_index,
            },
        )
        return _record("succeeded", content, block_id), block

    async def plan(self, req: PlanRequest) -> PlanOutcome:
        outcome = await self.assistant.plan(
            req.goal, list(req.clarifications), list(req.context_blocks)
        )
        if not outcome.ok or outcome.graph is None:
            return outcome

        init_ids = frozenset(b.id for b in req.context_blocks)
        errors = validate_task_graph(outcome.graph, initial_block_ids=init_ids)
        if errors:
            return PlanOutcome(
                ok=False,
                graph=outcome.graph,
                error="任务图校验失败: " + "; ".join(errors),
                raw=outcome.raw,
            )
        return outcome

    async def run_graph(
        self,
        goal: str,
        graph: TaskGraph,
        *,
        initial_blocks: list[DataBlock] | None = None,
        log: LogFn | None = None,
        on_progress: Callable[[str, str, int, str], None] | None = None,
    ) -> GraphRunResult:
        init_ids = frozenset(b.id for b in (initial_blocks or []))
        errors = validate_task_graph(graph, initial_block_ids=init_ids)
        if errors:
            return GraphRunResult(
                ok=False,
                goal=goal,
                summary=graph.summary,
                error="任务图校验失败: " + "; ".join(errors),
            )
        runtime = GraphRuntime(log=log, on_progress=on_progress)
        return await runtime.run(goal, graph, initial_blocks=initial_blocks)

    # ---------- Server Center / UI ----------

    async def _push(self, msg_type: str, message: dict[str, Any]) -> None:
        if not self.server:
            return
        try:
            await self.server.send_message(
                msg_type=msg_type,
                message=message,
                target="user_ui",
            )
        except Exception:
            logger.exception("Failed to push %s to Server Center", msg_type)

    async def handle_incoming_message(self, data: dict[str, Any]) -> None:
        if data.get("name") != "user_ui":
            return
        target = data.get("target", "")
        if target not in MODULE_ALIASES and target != MODULE_ID and target != MODULE_NAME:
            return

        msg_type = data.get("msg_type", "text")
        if msg_type not in UI_MSG_TYPES:
            return

        message = data.get("message") or {}
        payload = message.get("payload") or message
        action = str(payload.get("action") or message.get("action") or "").strip()
        request_id = str(payload.get("request_id") or message.get("request_id") or "")

        if not action:
            # 纯文本：当作「仅目标 → 直接 clarify 一轮」的快捷入口不处理，避免误触
            return

        try:
            if action == "clarify":
                await self._ui_clarify(payload, request_id)
            elif action == "env_probe":
                await self._ui_env_probe(payload, request_id)
            elif action == "plan":
                await self._ui_plan(payload, request_id)
            elif action == "run_graph":
                await self._ui_run_graph(payload, request_id)
            else:
                logger.warning("Unknown planning action: %s", action)
        except Exception:
            logger.exception("planning UI handler failed action=%s", action)
            await self._push(
                MSG_PLAN_RESULT,
                {
                    "ok": False,
                    "error": f"规划处理异常（action={action}）",
                    "request_id": request_id,
                    "goal": str(payload.get("goal") or ""),
                    "summary": "",
                    "status": "failed",
                    "graph": None,
                },
            )

    async def _ui_clarify(self, payload: dict[str, Any], request_id: str) -> None:
        req = ClarifyRequest.model_validate(
            {
                "goal": payload.get("goal") or "",
                "history": payload.get("history") or [],
                "env_records": payload.get("env_records") or [],
                "round_index": int(payload.get("round_index") or 1),
            }
        )
        outcome = await self.clarify(req)
        body = outcome.model_dump()
        body["request_id"] = request_id
        body["goal"] = req.goal
        body["round_index"] = req.round_index
        await self._push(MSG_CLARIFY_RESULT, body)

    async def _ui_env_probe(self, payload: dict[str, Any], request_id: str) -> None:
        round_index = int(payload.get("round_index") or 1)
        raw_queries = payload.get("queries") or []
        if not isinstance(raw_queries, list) or not raw_queries:
            # 单条兼容
            q = payload.get("query")
            if isinstance(q, dict):
                raw_queries = [q]
        results: list[dict[str, Any]] = []
        for item in raw_queries:
            if not isinstance(item, dict):
                continue
            block_id = str(item.get("block_id") or "").strip()
            query = EnvQuery.model_validate(
                {
                    "id": item.get("id"),
                    "instruction": item.get("instruction"),
                    "purpose": item.get("purpose") or "",
                }
            )
            if not block_id:
                block_id = f"env_{query.id}"
            rec, blk = await self.run_env_query(
                query, block_id=block_id, round_index=round_index
            )
            results.append(
                {
                    "record": rec.model_dump(),
                    "block": blk.model_dump() if blk is not None else None,
                }
            )
        await self._push(
            MSG_ENV_PROBE_RESULT,
            {
                "request_id": request_id,
                "round_index": round_index,
                "results": results,
            },
        )

    async def _ui_plan(self, payload: dict[str, Any], request_id: str) -> None:
        req = PlanRequest.model_validate(
            {
                "goal": payload.get("goal") or "",
                "clarifications": payload.get("clarifications")
                or payload.get("history")
                or [],
                "context_blocks": payload.get("context_blocks") or [],
            }
        )
        outcome = await self.plan(req)
        graph_dump = outcome.graph.model_dump(by_alias=True) if outcome.graph else None
        await self._push(
            MSG_PLAN_RESULT,
            {
                "ok": outcome.ok,
                "error": outcome.error,
                "request_id": request_id,
                "goal": compose_goal(req.goal, list(req.clarifications)),
                "summary": (outcome.graph.summary if outcome.graph else "") or "",
                "status": "draft" if outcome.ok else "failed",
                "graph": graph_dump,
                "raw": outcome.raw,
            },
        )

    async def _ui_run_graph(self, payload: dict[str, Any], request_id: str) -> None:
        goal = str(payload.get("goal") or "").strip()
        raw_graph = payload.get("graph") or {}
        graph = TaskGraph.model_validate(raw_graph)
        raw_blocks = payload.get("initial_blocks") or payload.get("context_blocks") or []
        initial_blocks = [DataBlock.model_validate(b) for b in raw_blocks if isinstance(b, dict)]

        loop = asyncio.get_running_loop()

        def on_progress(node_id: str, status: str, attempts: int, error: str) -> None:
            async def _send() -> None:
                await self._push(
                    MSG_PLAN_PROGRESS,
                    {
                        "request_id": request_id,
                        "node_id": node_id,
                        "status": status,
                        "attempts": attempts,
                        "error": error or "",
                    },
                )

            try:
                loop.create_task(_send())
            except RuntimeError:
                logger.exception("plan_progress schedule failed for %s", node_id)

        result = await self.run_graph(
            goal,
            graph,
            initial_blocks=initial_blocks,
            on_progress=on_progress,
        )
        body = result.model_dump()
        body["request_id"] = request_id
        body["status"] = "completed" if result.ok else "failed"
        await self._push(MSG_GRAPH_RUN_RESULT, body)
