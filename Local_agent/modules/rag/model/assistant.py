from __future__ import annotations

from modules.rag.model.prompts import DIRECT_ANSWER_HEADER, RAG_ANSWER_PROMPT, SYSTEM_PROMPT
from modules.rag.schemas import SourceItem
from shared.llm import get_llm_client


class RagAssistant:
    """RAG 本地小模型：阅读检索结果并总结，或直接拼接片段。"""

    def __init__(self) -> None:
        self.llm = get_llm_client("rag.summarize")

    async def summarize_answer(self, query: str, sources: list[SourceItem], *, history: list[dict[str, str]] | None = None) -> str:
        if not sources:
            return "知识库中未检索到与问题相关的内容，请先导入文档后再试。"

        context_blocks: list[str] = []
        for index, source in enumerate(sources, start=1):
            header = f"[{index}] {source.title or source.doc_id} (score={source.score:.2f})"
            context_blocks.append(f"{header}\n{source.snippet}")
        context = "\n\n".join(context_blocks)

        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            messages.extend(history[-6:])
        messages.append(
            {
                "role": "user",
                "content": RAG_ANSWER_PROMPT.format(query=query, context=context),
            }
        )
        return await self.llm.chat(messages)

    def direct_answer(self, query: str, sources: list[SourceItem]) -> str:
        if not sources:
            return "知识库中未检索到与问题相关的内容，请先导入文档后再试。"

        lines = [DIRECT_ANSWER_HEADER, f"问题：{query}", ""]
        for index, source in enumerate(sources, start=1):
            title = source.title or source.doc_id or f"片段{index}"
            lines.append(f"--- [{index}] {title} (score={source.score:.2f}) ---")
            lines.append(source.snippet)
            lines.append("")
        return "\n".join(lines).strip()
