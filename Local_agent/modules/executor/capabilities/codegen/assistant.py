from __future__ import annotations

import logging
import time

from modules.executor.capabilities.codegen.prompts import render_codegen_system, render_codegen_user
from modules.executor.content_extract import extract_fenced_blocks
from modules.executor.llm_slots import EXECUTOR_CODEGEN_SLOT
from shared.llm import get_llm_client

logger = logging.getLogger(__name__)

ACTION_TYPE = "code.generate"


def strip_code_response(text: str) -> str:
    """去掉模型可能附带的 markdown 围栏，保留纯代码。"""
    stripped = text.strip()
    blocks = extract_fenced_blocks(stripped)
    if blocks:
        return max(blocks, key=len) if len(blocks) > 1 else blocks[0]
    return stripped


class CodegenAssistant:
    """根据详细自然语言规格生成完整代码。"""

    def __init__(self) -> None:
        self.llm = get_llm_client(EXECUTOR_CODEGEN_SLOT)

    async def generate_code(self, spec_text: str) -> tuple[str | None, str, int]:
        """
        返回 (code, error_reason, duration_ms)。
        成功时 error_reason 为空。
        """
        spec = spec_text.strip()
        if not spec:
            return None, "代码生成规格不能为空", 0

        messages = [
            {"role": "system", "content": render_codegen_system()},
            {"role": "user", "content": render_codegen_user(spec)},
        ]

        started = time.perf_counter()
        try:
            raw = await self.llm.chat(messages)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - started) * 1000)
            return None, f"代码生成失败: {exc}", duration_ms

        duration_ms = int((time.perf_counter() - started) * 1000)
        code = strip_code_response(raw)
        if not code:
            return None, "模型未返回有效代码", duration_ms

        logger.info("codegen produced %d chars in %dms", len(code), duration_ms)
        return code, "", duration_ms
