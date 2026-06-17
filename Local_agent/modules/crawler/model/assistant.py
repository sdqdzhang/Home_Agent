from __future__ import annotations

from typing import Any

from shared.llm import get_llm_client
from modules.crawler.filters import FilterOutput
from modules.crawler.model.prompts import (
    CHAT_WITH_CONTEXT_PROMPT,
    CUSTOM_FILTER_PROMPT,
    JUDGE_CRAWL_PROMPT,
    PICK_FILTER_PROMPT,
    SYSTEM_PROMPT,
    TUNE_CONFIG_PROMPT,
)
from modules.crawler.strategies.base import CrawlResult


class CrawlerAssistant:
    """模块内本地模型助手。"""

    def __init__(self) -> None:
        self._pipeline_llm = get_llm_client("crawler.pipeline")
        self._chat_llm = get_llm_client("crawler.chat")

    async def judge_crawl(
        self,
        *,
        task: str,
        url: str,
        result: CrawlResult,
    ) -> dict[str, Any]:
        prompt = JUDGE_CRAWL_PROMPT.format(
            task=task,
            url=url,
            strategy=result.strategy,
            title=result.title,
            error=result.error,
            preview=result.preview(800),
        )
        return await self._pipeline_llm.chat_json(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=384,
        )

    async def tune_config(
        self,
        *,
        url: str,
        strategy: str,
        config: dict,
        error: str,
        suggestions: dict,
    ) -> dict[str, Any]:
        prompt = TUNE_CONFIG_PROMPT.format(
            url=url,
            strategy=strategy,
            config=config,
            error=error,
            suggestions=suggestions,
        )
        tuned = await self._pipeline_llm.chat_json(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=384,
        )
        return {**config, **tuned}

    async def pick_best_filter(
        self,
        *,
        task: str,
        url: str,
        candidates: list[FilterOutput],
    ) -> dict[str, Any]:
        payload = [
            {"name": c.name, "score": c.score, "preview": c.content[:500], "metadata": c.metadata}
            for c in candidates
        ]
        prompt = PICK_FILTER_PROMPT.format(task=task, url=url, candidates=payload)
        return await self._pipeline_llm.chat_json(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=256,
        )

    async def custom_filter(
        self,
        *,
        task: str,
        url: str,
        result: CrawlResult,
    ) -> dict[str, Any]:
        prompt = CUSTOM_FILTER_PROMPT.format(
            task=task,
            url=url,
            title=result.title,
            content=result.preview(6000),
        )
        return await self._pipeline_llm.chat_json(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
        )

    async def chat(self, user_message: str, history: list[dict[str, str]], context: str = "") -> str:
        system = CHAT_WITH_CONTEXT_PROMPT.format(context=context or "（无额外上下文）")
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return await self._chat_llm.chat(messages)
