from __future__ import annotations

import logging
from typing import Any

from shared.server_center.client import ServerCenterClient
from modules.processor import DEFAULT_MSG_TYPE, ID_PREFIX, MODULE_ALIASES
from modules.processor.ids import IdCounter
from modules.processor.model import ProcessorAssistant
from modules.processor.schemas import DataBlock, ProcessRequest, ProcessResult

logger = logging.getLogger(__name__)


class ProcessorService:
    """处理：requirement + DataBlock[] → 一个带系统 id 的 DataBlock。"""

    def __init__(self, server_client: ServerCenterClient | None = None) -> None:
        self.server = server_client
        self.ids = IdCounter(ID_PREFIX)
        self.assistant = ProcessorAssistant()

    async def process(self, req: ProcessRequest, *, push: bool = False) -> ProcessResult:
        requirement = req.requirement.strip()
        request_id = (req.request_id or "").strip()
        if not requirement:
            return ProcessResult(
                ok=False,
                requirement=req.requirement,
                inputs=list(req.blocks),
                error="总要求不能为空",
                request_id=request_id,
            )
        if not req.blocks:
            return ProcessResult(
                ok=False,
                requirement=requirement,
                inputs=[],
                error="至少需要一个 DataBlock",
                request_id=request_id,
            )

        block, err = await self.assistant.process(requirement, list(req.blocks))
        if err or block is None:
            result = ProcessResult(
                ok=False,
                requirement=requirement,
                inputs=list(req.blocks),
                error=err or "处理失败",
                request_id=request_id,
            )
            if push:
                await self._push_result(result)
            return result

        block.id = self.ids.next()
        result = ProcessResult(
            ok=True,
            requirement=requirement,
            inputs=list(req.blocks),
            output=block,
            request_id=request_id,
        )
        if push:
            await self._push_result(result)
        return result

    async def handle_incoming_message(self, data: dict[str, Any]) -> None:
        if data.get("name") != "user_ui":
            return
        target = data.get("target", "")
        if target not in MODULE_ALIASES:
            return

        msg_type = data.get("msg_type", "text")
        message = data.get("message") or {}

        if msg_type not in ("text", "process_request", "datablock"):
            return

        payload = message.get("payload") or message
        requirement = (
            payload.get("requirement")
            or message.get("requirement")
            or message.get("text")
            or ""
        )
        requirement = str(requirement).strip()
        raw_blocks = payload.get("blocks") or message.get("blocks") or []
        request_id = str(payload.get("request_id") or message.get("request_id") or "")
        if not requirement or not isinstance(raw_blocks, list) or not raw_blocks:
            return

        try:
            blocks = [DataBlock.model_validate(b) for b in raw_blocks]
            req = ProcessRequest(requirement=requirement, blocks=blocks, request_id=request_id)
        except Exception:
            logger.exception("Invalid process request from UI")
            return

        await self.process(req, push=True)

    async def _push_result(self, result: ProcessResult) -> None:
        if not self.server:
            return
        try:
            await self.server.send_message(
                msg_type=DEFAULT_MSG_TYPE,
                message=result.model_dump(),
                target="user_ui",
            )
        except Exception:
            logger.exception("Failed to push processor result to Server Center")
