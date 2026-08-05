from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

_TEST_DIR = Path(__file__).resolve().parent
_ROOT = _TEST_DIR.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.llm.client import LLMClient
from shared.llm.config import LLMSettings
from shared.llm.json_parse import (
    as_json_object,
    heuristic_loads,
    heuristic_prepare,
    try_parse_pipeline,
)


def test_strict_and_fence() -> None:
    obj, err = try_parse_pipeline('{"a": 1}', repair_enabled=False)
    assert err == ""
    assert obj == {"a": 1}

    fenced = '好的，结果如下：\n```json\n{"ok": true, "n": 2}\n```\n'
    obj, err = try_parse_pipeline(fenced, repair_enabled=False)
    assert err == ""
    assert obj == {"ok": True, "n": 2}


def test_trailing_comma_heuristic() -> None:
    raw = '{"a": 1, "b": [2, 3,],}'
    prepared = heuristic_prepare(raw)
    assert heuristic_loads(raw) == {"a": 1, "b": [2, 3]}
    assert ",}" not in prepared
    assert ",]" not in prepared


def test_wrapped_prose_slice() -> None:
    raw = '前缀废话 {"x": 1, "y": "z"} 后缀'
    assert heuristic_loads(raw) == {"x": 1, "y": "z"}


def test_smart_quotes() -> None:
    raw = "{“name”: “玲”}"
    assert heuristic_loads(raw) == {"name": "玲"}


def test_pipeline_rejects_blank() -> None:
    obj, err = try_parse_pipeline("   ", repair_enabled=False)
    assert obj is None
    assert "empty" in err


def test_as_json_object() -> None:
    assert as_json_object({"a": 1}) == {"a": 1}
    assert as_json_object([1, 2]) is None


def test_repair_stage_when_available() -> None:
    try:
        import json_repair  # noqa: F401
    except ImportError:
        print("skip test_repair_stage_when_available: json_repair not installed")
        return

    # 缺逗号：启发式通常修不好，依赖 json_repair
    raw = '{"a": 1 "b": 2}'
    obj, err = try_parse_pipeline(raw, repair_enabled=True)
    assert err == ""
    assert obj == {"a": 1, "b": 2}


def test_chat_json_llm_retry() -> None:
    settings = LLMSettings(
        json_repair_enabled=False,
        json_max_retries=1,
    )
    client = LLMClient(config=settings, slot="default.chat")
    client.chat = AsyncMock(
        side_effect=[
            "not-json-at-all",
            '{"recovered": true}',
        ]
    )

    async def _run() -> dict[str, Any]:
        return await client.chat_json(
            [{"role": "user", "content": "ping"}],
            repair_enabled=False,
            max_retries=1,
        )

    data = asyncio.run(_run())
    assert data == {"recovered": True}
    assert client.chat.await_count == 2
    second_messages = client.chat.await_args_list[1].args[0]
    assert second_messages[-1]["role"] == "user"
    assert "无法解析" in second_messages[-1]["content"]


def test_chat_json_exhausted() -> None:
    settings = LLMSettings(json_repair_enabled=False, json_max_retries=1)
    client = LLMClient(config=settings, slot="default.chat")
    client.chat = AsyncMock(return_value="still-broken")

    async def _run() -> None:
        await client.chat_json(
            [{"role": "user", "content": "ping"}],
            repair_enabled=False,
            max_retries=1,
        )

    try:
        asyncio.run(_run())
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "LLM JSON parse failed" in str(exc)
    assert client.chat.await_count == 2


if __name__ == "__main__":
    test_strict_and_fence()
    test_trailing_comma_heuristic()
    test_wrapped_prose_slice()
    test_smart_quotes()
    test_pipeline_rejects_blank()
    test_as_json_object()
    test_repair_stage_when_available()
    test_chat_json_llm_retry()
    test_chat_json_exhausted()
    print("ok")
