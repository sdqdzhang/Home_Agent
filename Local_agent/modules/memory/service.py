from __future__ import annotations

import logging
from typing import Any

from shared.server_center.client import ServerCenterClient
from modules.memory import DEFAULT_MSG_TYPE, MODULE_ALIASES
from modules.memory.config import memory_settings
from modules.memory.model import DialogueSummarizer, ImportanceAssessor, MemoryReflector, MemoryTagger
from modules.memory.index.memory_store import MemoryVectorStore
from modules.memory.recall.retriever import MemoryRetriever
from modules.memory.schemas import (
    CoreMemoryItem,
    CoreMemoryUpsert,
    IngestDialogueRequest,
    IngestDialogueResponse,
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
        self.summarizer = DialogueSummarizer()
        self.tagger = MemoryTagger()

    def status(self) -> MemoryStatusResponse:
        return MemoryStatusResponse(
            working_count=self.working.count(),
            working_max_size=memory_settings.working_max_size,
            working_keep_after_consolidate=memory_settings.working_keep_after_consolidate,
            archive_count=self.archive.count(),
            core_count=self.core.count(),
            context_limit=memory_settings.context_limit,
        )

    async def _resolve_tags(
        self,
        content: str,
        *,
        kind: str,
        manual_tags: list[str] | None = None,
    ) -> list[str]:
        return await self.tagger.tag(content, kind=kind, manual_tags=manual_tags)

    async def observe(self, request: ObserveRequest | dict[str, Any]) -> ObserveResponse:
        if isinstance(request, dict):
            request = ObserveRequest.model_validate(request)

        content = request.content.strip()
        tags = await self._resolve_tags(content, kind=request.kind, manual_tags=request.tags)
        importance, assess_reason = await self.assessor.rate(content)
        min_imp = memory_settings.observe_min_importance

        if importance < min_imp:
            reason = (
                f"importance {importance:.1f} < {min_imp:.1f}；{assess_reason}"
            ).strip("；")
            logger.info("observe rejected: %s | %s", reason, content[:80])
            return ObserveResponse(
                content=content,
                tags=tags,
                importance=importance,
                kind=request.kind,
                working_count=self.working.count(),
                consolidated=False,
                accepted=False,
                rejected_reason=reason,
            )

        meta = dict(request.metadata)
        meta["assess_reason"] = assess_reason
        meta["tags"] = tags

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
            tags=tags,
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
            tags=tags,
            importance=importance,
            kind=request.kind,
            working_count=self.working.count(),
            consolidated=consolidated,
            accepted=True,
        )

    async def ingest_dialogue(self, request: IngestDialogueRequest | dict[str, Any]) -> IngestDialogueResponse:
        if isinstance(request, dict):
            request = IngestDialogueRequest.model_validate(request)

        summary = await self.summarizer.summarize(request.dialogue)
        if not summary:
            raise ValueError("对话总结失败，未产出有效记忆句")

        observed = await self.observe(
            ObserveRequest(
                content=summary,
                kind="observation",
                tags=request.tags,
                metadata={"source": "dialogue_summary"},
            )
        )
        if not observed.accepted:
            raise ValueError(
                f"对话总结未达入库门槛：{observed.rejected_reason or 'importance too low'}"
            )
        return IngestDialogueResponse(
            summary=summary,
            memory_id=observed.memory_id,
            content=observed.content,
            tags=observed.tags,
            importance=observed.importance,
            kind=observed.kind,
            working_count=observed.working_count,
            consolidated=observed.consolidated,
        )

    async def recall(self, request: RecallRequest | dict[str, Any]) -> RecallResponse:
        if isinstance(request, dict):
            request = RecallRequest.model_validate(request)
        query_tags = request.tags
        if not query_tags:
            query_tags = await self.tagger.tag(request.query, kind="observation")
        items = self.retriever.recall(request.query, top_k=request.top_k, query_tags=query_tags)
        return RecallResponse(query=request.query, items=items)

    def get_context(self, *, min_importance: float | None = None) -> dict[str, Any]:
        """返回供 LLM 使用的工作记忆上下文（默认最多 context_limit 条）。"""
        floor = (
            memory_settings.context_min_importance
            if min_importance is None
            else float(min_importance)
        )
        rows = [
            item
            for item in self.working.list_for_context(memory_settings.context_limit * 2)
            if float(item.get("importance") or 0) >= floor
        ][: memory_settings.context_limit]
        core = self.core.list_all()
        lines = [
            f"- ({item['kind']}, {item['importance']:.1f}) "
            f"[{', '.join((item.get('metadata') or {}).get('tags') or [])}] "
            f"{item['content']}"
            for item in rows
        ]
        core_lines = [f"- [core:{c['key']}] {c['value']}" for c in core]
        text_parts = []
        if core_lines:
            text_parts.append("长期设定：\n" + "\n".join(core_lines))
        if lines:
            text_parts.append("相关记忆：\n" + "\n".join(lines))
        return {
            "working_memories": rows,
            "core_memories": core,
            "text": "\n\n".join(text_parts),
        }

    async def context_for_main(self, query: str = "", *, top_k: int = 3) -> dict[str, Any]:
        """供主对话注入：核心设定 + 高分工作记忆 + 与当前句相关的召回。"""
        base = self.get_context()
        recalled: list[dict[str, Any]] = []
        q = (query or "").strip()
        if q:
            try:
                result = await self.recall(RecallRequest(query=q, top_k=top_k))
                floor = memory_settings.context_min_importance
                for item in result.items:
                    if item.importance < floor:
                        continue
                    recalled.append(
                        {
                            "memory_id": item.memory_id,
                            "content": item.content,
                            "importance": item.importance,
                            "score": item.score,
                            "tags": item.tags,
                        }
                    )
            except Exception:
                logger.exception("context_for_main recall failed")

        # 合并去重：先 core/working 文本，再补召回里尚未出现的
        seen = {str(r.get("content") or "").strip() for r in base.get("working_memories") or []}
        extra_lines: list[str] = []
        for item in recalled:
            content = str(item.get("content") or "").strip()
            if not content or content in seen:
                continue
            seen.add(content)
            extra_lines.append(
                f"- (recall, {float(item.get('importance') or 0):.1f}) {content}"
            )

        text = str(base.get("text") or "").strip()
        if extra_lines:
            block = "可能相关的检索记忆：\n" + "\n".join(extra_lines)
            text = f"{text}\n\n{block}".strip() if text else block

        return {
            "working_memories": base.get("working_memories") or [],
            "core_memories": base.get("core_memories") or [],
            "recalled": recalled,
            "text": text,
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
        tags = await self._resolve_tags(content, kind="insight")
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
            "tags": tags,
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
            tags=tags,
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
                tags=tags,
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

    def inspect_archive(self) -> dict[str, Any]:
        from modules.memory.config import memory_settings

        items = self.archive.list_all()
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            mid = item["memory_id"]
            grouped.setdefault(mid, []).append(item)

        return {
            "collection": memory_settings.archive_collection,
            "chroma_dir": str(memory_settings.chroma_dir),
            "chroma_count": len(items),
            "memory_count": len(grouped),
            "working_count": self.working.count(),
            "core_count": self.core.count(),
            "items": items,
            "grouped": grouped,
        }

    def clear_all_data(self, *, include_core: bool = True) -> dict[str, int]:
        chroma_removed = self.archive.clear()
        working_removed = self.working.clear_all()
        core_removed = self.core.clear_all() if include_core else 0
        return {
            "chroma_removed": chroma_removed,
            "working_removed": working_removed,
            "core_removed": core_removed,
        }

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

        if action == "ingest_dialogue":
            await self.ingest_dialogue(
                IngestDialogueRequest(dialogue=payload.get("dialogue") or message.get("text", ""))
            )
            return

        if action == "reflect":
            await self.reflect(ReflectRequest(limit=int(payload.get("limit", 10))))
            return

        if action == "recall":
            result = await self.recall(
                RecallRequest(
                    query=payload.get("query") or message.get("text", ""),
                    tags=payload.get("tags") or [],
                )
            )
            if self.server:
                lines = [
                    f"[{item.score:.3f}|tag={item.tag_score:.2f}] {item.content}"
                    for item in result.items
                ]
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

        result = await self.recall(RecallRequest(query=text))
        if self.server:
            lines = [f"[{item.score:.3f}|tag={item.tag_score:.2f}] {item.content}" for item in result.items]
            await self.server.send_message(
                msg_type="text",
                message={
                    "text": "\n".join(lines) if lines else "（无匹配记忆）",
                    "role": "agent",
                    "reply_to": data.get("id"),
                },
            )
