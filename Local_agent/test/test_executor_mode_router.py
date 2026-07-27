from __future__ import annotations

from modules.executor.mode_router import (
    has_file_attachment,
    parse_route_response,
    route_instruction_text,
)


def test_has_file_attachment():
    assert has_file_attachment(None) is False
    assert has_file_attachment("") is False
    assert has_file_attachment("body") is True


def test_route_instruction_strips_fenced():
    text = "把下面写到 a.py\n```python\nprint(1)\n```"
    instruction, has_fenced = route_instruction_text(text)
    assert has_fenced is True
    assert "print(1)" not in instruction
    assert "a.py" in instruction


def test_parse_route_ok():
    mode, err = parse_route_response({"ok": True, "mode": "command"})
    assert mode == "command"
    assert err == ""


def test_parse_route_reject_unknown():
    mode, err = parse_route_response({"ok": True, "mode": "fly"})
    assert mode is None
    assert "未知" in err


def test_parse_route_uncertain():
    mode, err = parse_route_response({"ok": False, "reason": "指令含糊"})
    assert mode is None
    assert "含糊" in err
