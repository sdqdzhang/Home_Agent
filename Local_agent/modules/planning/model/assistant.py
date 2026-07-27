"""规划模块 LLM 助手。"""

from __future__ import annotations

import logging

from modules.planning.model.prompts import (
    build_clarify_system,
    build_plan_system,
    render_clarify_user,
    render_plan_user,
)
from modules.planning.schemas import (
    ClarifyAnswer,
    ClarifyOutcome,
    ClarifyQuestion,
    EnvProbeRecord,
    EnvQuery,
    PlanOutcome,
    TaskGraph,
    compose_goal,
)
from modules.planning.validate import workspace_abs
from modules.processor.schemas import DataBlock
from shared.llm import get_llm_client

logger = logging.getLogger(__name__)

CLARIFY_SLOT = "planning.clarify"
PLAN_SLOT = "planning.plan"


class PlanningAssistant:
    def __init__(
        self,
        clarify_slot: str = CLARIFY_SLOT,
        plan_slot: str = PLAN_SLOT,
    ) -> None:
        self.clarify_slot = clarify_slot
        self.plan_slot = plan_slot

    async def clarify(
        self,
        goal: str,
        history: list[ClarifyAnswer],
        env_records: list[EnvProbeRecord] | None = None,
        round_index: int = 1,
    ) -> tuple[ClarifyOutcome | None, str]:
        llm = get_llm_client(self.clarify_slot)
        hist = [
            {"question": h.question or h.question_id, "answer": h.answer}
            for h in history
        ]
        envs = [
            {
                "instruction": r.instruction,
                "purpose": r.purpose,
                "status": r.status,
                "block_id": r.block_id,
                "summary": r.summary,
            }
            for r in (env_records or [])
        ]
        ws = workspace_abs()
        messages = [
            {"role": "system", "content": build_clarify_system(ws)},
            {
                "role": "user",
                "content": render_clarify_user(
                    goal, hist, envs, round_index, workspace_abs=ws
                ),
            },
        ]
        try:
            data = await llm.chat_json(messages)
        except Exception as exc:
            logger.exception("Planning clarify LLM failed")
            return None, f"质询模型调用失败: {exc}"

        if not isinstance(data, dict):
            return None, "质询返回不是 JSON 对象"

        try:
            ready = bool(data.get("ready"))
            raw_questions = data.get("questions") or []
            questions: list[ClarifyQuestion] = []
            if isinstance(raw_questions, list):
                for item in raw_questions:
                    if not isinstance(item, dict):
                        continue
                    # 模型常漏写 choices：补默认选项，避免整轮信息收集失败
                    patched = dict(item)
                    choices = patched.get("choices")
                    if not isinstance(choices, list) or not [c for c in choices if str(c).strip()]:
                        patched["choices"] = ["按你的理解继续", "我再补充说明"]
                    try:
                        questions.append(ClarifyQuestion.model_validate(patched))
                    except Exception as qerr:
                        logger.warning("Skip invalid clarify question %s: %s", item, qerr)
                        continue
            raw_envs = data.get("env_queries") or []
            env_queries: list[EnvQuery] = []
            if isinstance(raw_envs, list):
                for item in raw_envs:
                    if not isinstance(item, dict):
                        continue
                    try:
                        env_queries.append(EnvQuery.model_validate(item))
                    except Exception as eerr:
                        logger.warning("Skip invalid env query %s: %s", item, eerr)
                        continue
            outcome = ClarifyOutcome(
                ready=ready,
                questions=[] if ready else questions,
                env_queries=[] if ready else env_queries,
                note=str(data.get("note") or ""),
            )
            if not outcome.ready and not outcome.questions and not outcome.env_queries:
                return None, "模型声称需要收集信息但未给出 questions/env_queries"
            return outcome, ""
        except Exception as exc:
            return None, f"信息收集结果校验失败: {exc}"

    async def plan(
        self,
        goal: str,
        clarifications: list[ClarifyAnswer],
        context_blocks: list[DataBlock] | None = None,
    ) -> PlanOutcome:
        llm = get_llm_client(self.plan_slot)
        ws = workspace_abs()
        effective_goal = compose_goal(goal, list(clarifications))
        ctx = [
            {
                "id": b.id,
                "type": b.type,
                "content": b.content,
                "metadata": b.metadata,
            }
            for b in (context_blocks or [])
        ]
        messages = [
            {"role": "system", "content": build_plan_system(ws)},
            {"role": "user", "content": render_plan_user(effective_goal, ws, ctx)},
        ]

        last_err = ""
        data = None
        for attempt in range(1, 3):
            try:
                data = await llm.chat_json(messages)
                break
            except Exception as exc:
                last_err = str(exc)
                logger.warning("Planning plan LLM attempt %d failed: %s", attempt, exc)
                data = None
        if data is None:
            return PlanOutcome(ok=False, error=f"规划模型调用失败: {last_err}")

        if not isinstance(data, dict):
            return PlanOutcome(ok=False, error="规划返回不是 JSON 对象", raw={"value": data})

        try:
            graph = TaskGraph.model_validate(data)
        except Exception as exc:
            return PlanOutcome(ok=False, error=f"任务图结构校验失败: {exc}", raw=data)

        return PlanOutcome(ok=True, graph=graph, raw=data)
