from __future__ import annotations

import logging
from typing import Any

from modules.processor.schemas import DataBlock
from modules.processor.model.prompts import PROCESS_SYSTEM, render_user
from shared.llm import get_llm_client

logger = logging.getLogger(__name__)

SLOT_KEY = "processor.process"


class ProcessorAssistant:
    def __init__(self, slot_key: str = SLOT_KEY) -> None:
        self.slot_key = slot_key

    @staticmethod
    def blocks_for_llm(blocks: list[DataBlock]) -> list[dict[str, Any]]:
        """进 LLM 时去掉 id。"""
        out: list[dict[str, Any]] = []
        for b in blocks:
            out.append(
                {
                    "type": b.type,
                    "content": b.content,
                    "producer": b.producer,
                    "metadata": dict(b.metadata or {}),
                }
            )
        return out

    async def process(self, requirement: str, blocks: list[DataBlock]) -> tuple[DataBlock | None, str]:
        llm = get_llm_client(self.slot_key)
        messages = [
            {"role": "system", "content": PROCESS_SYSTEM},
            {
                "role": "user",
                "content": render_user(requirement, self.blocks_for_llm(blocks)),
            },
        ]
        try:
            data = await llm.chat_json(messages)
        except Exception as exc:
            logger.exception("Processor LLM call failed")
            return None, f"模型调用失败: {exc}"

        if not isinstance(data, dict):
            return None, "模型返回格式无效（需要 JSON 对象）"

        # 系统独占 id；LLM 若带了也丢弃
        data.pop("id", None)

        raw_type = data.get("type")
        raw_content = data.get("content")
        if raw_type is None or raw_content is None:
            return None, "模型返回缺少 type 或 content"

        producer = data.get("producer")
        if producer is None or str(producer).strip() == "":
            producer = "processor"

        metadata = data.get("metadata")
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            return None, "模型返回的 metadata 必须是对象"

        try:
            block = DataBlock(
                id="",  # 由 service 分配
                type=str(raw_type),
                content=str(raw_content),
                producer=str(producer).strip(),
                metadata=metadata,
            )
        except Exception as exc:
            return None, f"结果数据块校验失败: {exc}"

        return block, ""
