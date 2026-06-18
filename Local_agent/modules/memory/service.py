from __future__ import annotations

import logging
from typing import Any

from shared.server_center.client import ServerCenterClient
from modules.memory import DEFAULT_MSG_TYPE, MODULE_ALIASES
from modules.memory.config import memory_settings
from modules.memory.model import ImportanceAssessor, MemoryReflector
from modules.memory.index.memory_store import MemoryVectorStore
from modules.memory.recall.retriever import MemoryRetriever
from modules.memory.schemas import (
    CoreMemoryItem,
    CoreMemoryUpsert,
    MemoryStatusResponse,
    ObserveRequest,
    ObserveResponse,
    RecallRequest,
    RecallResponse,
    ReflectInsight,
    ReflectRequest,
    ReflectResponse,
)
from modules.memory.storage import CoreMemoryStore, WorkingMemoryStore

logger = logging.getLogger(__name__)


class MemoryService:
    """记忆服务：观察打分、工作记忆压缩、向量归档、三维检索、手动反思。"""

    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        memory_settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.server = server_client
        self.working = WorkingMemoryStore(memory_settings.db_path)
        self.core = CoreMemoryStore(memory_settings.db_path)
        self.archive = MemoryVectorStore()
        self.retriever = MemoryRetriever(self.archive)
        self.assessor = ImportanceAssessor()
        self.reflector = MemoryReflector()

    def status(self) -> MemoryStatusResponse:
        return MemoryStatusResponse(
            working_count=self.working.count(),
            working_max_size=memory_settings.working_max_size,
            working_keep_after_consolidate=memory_settings.working_keep_after_consolidate,
            archive_count=self.archive.count(),
            core_count=self.core.count(),
            context_limit=memory_settings.context_limit,
        )

    async def observe(self, request: ObserveRequest | dict[str, Any]) -> ObserveResponse:
        if isinstance(request, dict):
            request = ObserveRequest.model_validate(request)

        content = request.content.strip()
        importance, assess_reason = await self.assessor.rate(content)

        meta = dict(request.metadata)
        meta["assess_reason"] = assess_reason

        row = self.working.add(
            content,
            importance=importance,
            kind=request.kind,
            metadata=meta,
        )
        memory_id = row["id"]
        created_at = row["created_at"]

        self.archive.add_memory(
            memory_id=memory_id,
            content=content,
            importance=importance,
            kind=request.kind,
            created_at=created_at,
            metadata=meta,
        )

        consolidated = False
        removed = self.working.consolidate(
            max_size=memory_settings.working_max_size,
            keep=memory_settings.working_keep_after_consolidate,
        )
        if removed > 0:
            consolidated = True
            logger.info("Working memory consolidated: removed %s entries", removed)

        return ObserveResponse(
            memory_id=memory_id,
            content=content,
            importance=importance,
            kind=request.kind,
            working_count=self.working.count(),
            consolidated=consolidated,
        )

    def recall(self, request: RecallRequest | dict[str, Any]) -> RecallResponse:
        if isinstance(request, dict):
            request = RecallRequest.model_validate(request)
        items = self.retriever.recall(request.query, top_k=request.top_k)
        return RecallResponse(query=request.query, items=items)

    def get_context(self) -> dict[str, Any]:
        """返回供 LLM 使用的工作记忆上下文（默认最多 context_limit 条）。"""
        rows = self.working.list_for_context(memory_settings.context_limit)
        core = self.core.list_all()
        lines = [f"- ({item['kind']}, {item['importance']:.1f}) {item['content']}" for item in rows]
        return {
            "working_memories": rows,
            "core_memories": core,
            "text": "\n".join(lines) if lines else "",
        }

    async def reflect(self, request: ReflectRequest | dict[str, Any] | None = None) -> ReflectResponse:
        if request is None:
            request = ReflectRequest()
        elif isinstance(request, dict):
            request = ReflectRequest.model_validate(request)

        observations = self.working.list_recent_observations(limit=request.limit)
        consumed_ids = [item["id"] for item in observations]

        if not observations:
            return ReflectResponse(success=False, reason="无 observation 流水账，无法反思")

        synthesized = await self.reflector.synthesize(observations)
        if not synthesized:
            return ReflectResponse(
                success=False,
                consumed_ids=consumed_ids,
                reason="反思模型未产出有效洞察",
            )

        content = synthesized["content"]
        tag = synthesized["tag"]
        importance, assess_reason = await self.assessor.rate(content)

        if importance < memory_settings.reflection_min_importance:
            return ReflectResponse(
                success=False,
                consumed_ids=consumed_ids,
                reason=f"反思评分 {importance:.1f} 低于阈值 {memory_settings.reflection_min_importance}，视为无效反思",
            )

        removed_count = self.working.delete_by_ids(consumed_ids)

        meta = {
            "assess_reason": assess_reason,
            "tag": tag,
            "source_count": len(consumed_ids),
            "source_ids": consumed_ids,
        }
        row = self.working.add(
            content,
            importance=importance,
            kind="insight",
            metadata=meta,
        )
        memory_id = row["id"]
        created_at = row["created_at"]

        self.archive.add_memory(
            memory_id=memory_id,
            content=content,
            importance=importance,
            kind="insight",
            created_at=created_at,
            metadata=meta,
        )

        pushed = False
        if self.server:
            try:
                await self.server.send_message(
                    msg_type=DEFAULT_MSG_TYPE,
                    message={
                        "key": f"insight_{memory_id}",
                        "summary": content,
                        "importance": importance,
                        "kind": "insight",
                        "tag": tag,
                    },
                )
                pushed = True
            except Exception:
                logger.exception("Failed to push memory_record")

        logger.info(
            "Reflection succeeded: removed %s observations, wrote insight %s (importance=%.1f)",
            removed_count,
            memory_id,
            importance,
        )

        return ReflectResponse(
            success=True,
            insight=ReflectInsight(
                memory_id=memory_id,
                tag=tag,
                content=content,
                importance=importance,
                assess_reason=assess_reason,
            ),
            consumed_ids=consumed_ids,
            removed_count=removed_count,
            pushed=pushed,
        )

    def upsert_core(self, body: CoreMemoryUpsert | dict[str, Any]) -> CoreMemoryItem:
        if isinstance(body, dict):
            body = CoreMemoryUpsert.model_validate(body)
        row = self.core.upsert(body.key, body.value)
        return CoreMemoryItem(**row)

    def list_core(self) -> list[CoreMemoryItem]:
        return [CoreMemoryItem(**row) for row in self.core.list_all()]

    def delete_core(self, key: str) -> bool:
        return self.core.delete(key)

    async def handle_incoming_message(self, data: dict[str, Any]) -> None:
        if data.get("name") != "user_ui":
            return
        if data.get("target") not in MODULE_ALIASES:
            return
        if data.get("msg_type", "text") != "text":
            return

        message = data.get("message") or {}
        payload = message.get("payload") or {}
        action = payload.get("action")

        if action == "observe":
            await self.observe(
                ObserveRequest(
                    content=payload.get("content") or message.get("text", ""),
                    kind=payload.get("kind", "observation"),
                )
            )
            return

        if action == "reflect":
            await self.reflect(ReflectRequest(limit=int(payload.get("limit", 10))))
            return

        if action == "recall":
            result = self.recall(RecallRequest(query=payload.get("query") or message.get("text", "")))
            if self.server:
                lines = [f"[{item.score:.3f}] {item.content}" for item in result.items]
                await self.server.send_message(
                    msg_type="text",
                    message={
                        "text": "\n".join(lines) if lines else "（无匹配记忆）",
                        "role": "agent",
                        "reply_to": data.get("id"),
                    },
                )
            return

        text = (message.get("text") or "").strip()
        if not text:
            return

        result = self.recall(RecallRequest(query=text))
        if self.server:
            lines = [f"[{item.score:.3f}] {item.content}" for item in result.items]
            await self.server.send_message(
                msg_type="text",
                message={
                    "text": "\n".join(lines) if lines else "（无匹配记忆）",
                    "role": "agent",
                    "reply_to": data.get("id"),
                },
            )
