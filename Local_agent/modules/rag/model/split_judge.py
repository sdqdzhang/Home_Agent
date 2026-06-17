from __future__ import annotations

from openai import AsyncOpenAI

from modules.rag.config import rag_settings
from modules.rag.model.split_prompts import TOPIC_SWITCH_SYSTEM, TOPIC_SWITCH_USER
from shared.llm.config import llm_settings


class SemanticSplitJudge:
    """调用本地小模型判断相邻上下文是否应切分。"""

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            base_url=llm_settings.base_url,
            api_key=llm_settings.api_key,
            timeout=llm_settings.timeout,
        )
        self.model = rag_settings.split_model

    async def topic_switch(self, prev_context: str, next_unit: str) -> bool:
        prev_tail = prev_context[-600:] if len(prev_context) > 600 else prev_context
        messages = [
            {"role": "system", "content": TOPIC_SWITCH_SYSTEM},
            {
                "role": "user",
                "content": TOPIC_SWITCH_USER.format(prev=prev_tail, next=next_unit),
            },
        ]
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.0,
            max_tokens=8,
        )
        raw = (response.choices[0].message.content or "").strip().upper()
        if raw.startswith("YES"):
            return True
        if raw.startswith("NO"):
            return False
        return "YES" in raw and "NO" not in raw
