from __future__ import annotations

from modules.executor.runner import decode_subprocess_output


def test_decode_utf8_preferred():
    assert decode_subprocess_output("你好".encode("utf-8")) == "你好"


def test_decode_fallback_gbk():
    raw = "Windows 音频设备图形隔离".encode("gbk")
    assert decode_subprocess_output(raw) == "Windows 音频设备图形隔离"


def test_decode_empty():
    assert decode_subprocess_output(b"") == ""


def test_decode_ascii():
    assert decode_subprocess_output(b"Running  Appinfo") == "Running  Appinfo"
