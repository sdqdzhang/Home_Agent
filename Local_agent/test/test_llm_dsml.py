"""Tests for DeepSeek DSML tool-call parse/strip."""

from __future__ import annotations

import json

from shared.llm.dsml import heal_dsml_message, parse_dsml_tool_calls, strip_dsml


SAMPLE_INVOKE = """输出里混入了文件，我来只筛选文件夹再输出一次。
<｜DSML｜tool_calls>
<｜DSML｜invoke name="executor_run">
<｜DSML｜parameter name="instruction" string="true">使用 PowerShell 列出文件夹</｜DSML｜parameter>
</｜DSML｜invoke>
</｜DSML｜tool_calls>
"""

SAMPLE_DOUBLE_PIPE = """先说明一下。
<｜｜DSML｜｜tool_calls>
<｜｜DSML｜｜invoke name="executor_run">
<｜｜DSML｜｜parameter name="instruction" string="true">列出目录</｜｜DSML｜｜parameter>
</｜｜DSML｜｜invoke>
</｜｜DSML｜｜tool_calls>
"""


def test_strip_keeps_preamble():
    assert strip_dsml(SAMPLE_INVOKE) == "输出里混入了文件，我来只筛选文件夹再输出一次。"


def test_parse_invoke_parameter():
    calls = parse_dsml_tool_calls(SAMPLE_INVOKE)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "executor_run"
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["instruction"] == "使用 PowerShell 列出文件夹"


def test_parse_double_pipe_variant():
    calls = parse_dsml_tool_calls(SAMPLE_DOUBLE_PIPE)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "executor_run"
    args = json.loads(calls[0]["function"]["arguments"])
    assert args["instruction"] == "列出目录"


def test_heal_recovers_when_no_structured_calls():
    content, calls = heal_dsml_message(SAMPLE_INVOKE, None)
    assert "DSML" not in content
    assert content.startswith("输出里")
    assert len(calls) == 1


def test_heal_strips_even_when_structured_present():
    existing = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "executor_run", "arguments": "{}"},
        }
    ]
    content, calls = heal_dsml_message(SAMPLE_INVOKE, existing)
    assert "DSML" not in content
    assert calls == existing


def test_plain_text_untouched():
    content, calls = heal_dsml_message("普通回复，没有工具。", None)
    assert content == "普通回复，没有工具。"
    assert calls == []
