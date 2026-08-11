from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from pydantic import ValidationError

from modules.executor.capabilities import CAPABILITIES, EXECUTOR_MODES
from modules.executor.file_ops import format_directory_tree, search_content_in_file, search_files_by_name
from modules.executor.runner import run_file_read, run_file_write
from modules.executor.schemas import ExecuteRequest
from modules.executor.security_map import security_command_for_action
from modules.executor.schemas import (
    ContentSearchAction,
    DirBrowseAction,
    FileDeleteAction,
    FileReadAction,
    FileSearchAction,
    FileWriteAction,
)


def test_executor_modes_count():
    assert len(EXECUTOR_MODES) == 8
    assert set(CAPABILITIES) == set(EXECUTOR_MODES)


def test_execute_request_file_modes():
    req = ExecuteRequest(action_text="read README.md", mode="read_file")
    assert req.mode == "read_file"


def test_execute_request_mode_defaults_to_auto():
    req = ExecuteRequest(action_text="列出当前目录")
    assert req.mode is None


def test_security_pseudo_commands():
    assert security_command_for_action(FileReadAction(path="a.txt")).startswith("executor:file.read")
    assert security_command_for_action(FileWriteAction(path="a.txt")).startswith("executor:file.write")
    assert security_command_for_action(FileDeleteAction(path="a.txt")).startswith("executor:file.delete")
    assert security_command_for_action(DirBrowseAction(path=".")).startswith("executor:dir.browse")
    assert security_command_for_action(FileSearchAction(pattern="*.py", root=".")).startswith(
        "executor:file.search"
    )
    assert security_command_for_action(
        ContentSearchAction(path="a.py", query="secret")
    ).startswith("executor:content.search")


def test_file_ops_tree_and_search():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "README.md").write_text("alpha\nJWT_SECRET=1\nomega\n", encoding="utf-8")
        (root / "sub").mkdir()
        (root / "sub" / "docker-compose.yml").write_text("x", encoding="utf-8")

        tree = format_directory_tree(root, max_depth=3)
        assert "README.md" in tree

        found = search_files_by_name("docker-compose.yml", root)
        assert any("docker-compose.yml" in p for p in found)

        snippet = search_content_in_file(root / "README.md", "JWT_SECRET", context_lines=1)
        assert "JWT_SECRET" in snippet
        assert "行" in snippet


def test_file_read_action_rejects_inverted_range():
    try:
        FileReadAction(path="a.txt", start_line=10, end_line=5)
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


def test_file_read_action_rejects_non_positive_lines():
    try:
        FileReadAction(path="a.txt", start_line=0)
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass
    try:
        FileReadAction(path="a.txt", end_line=0)
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


def test_run_file_read_line_ranges():
    async def _run() -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.txt"
            path.write_text("L1\nL2\nL3\nL4\nL5\n", encoding="utf-8")

            full = await run_file_read(FileReadAction(path=str(path)))
            assert full.exit_code == 0
            assert full.stdout == "L1\nL2\nL3\nL4\nL5\n"

            clipped = await run_file_read(FileReadAction(path=str(path), start_line=1, end_line=500))
            assert clipped.exit_code == 0
            assert clipped.stdout == "L1\nL2\nL3\nL4\nL5"

            past_eof = await run_file_read(FileReadAction(path=str(path), start_line=100, end_line=200))
            assert past_eof.exit_code == 0
            assert past_eof.stdout == ""

            from_start = await run_file_read(FileReadAction(path=str(path), start_line=3))
            assert from_start.exit_code == 0
            assert from_start.stdout == "L3\nL4\nL5"

            first_two = await run_file_read(FileReadAction(path=str(path), end_line=2))
            assert first_two.exit_code == 0
            assert first_two.stdout == "L1\nL2"

            mid = await run_file_read(FileReadAction(path=str(path), start_line=2, end_line=4))
            assert mid.exit_code == 0
            assert mid.stdout == "L2\nL3\nL4"

    asyncio.run(_run())


def test_file_write_action_rejects_inverted_range():
    try:
        FileWriteAction(path="a.txt", start_line=10, end_line=5)
        raise AssertionError("expected ValidationError")
    except ValidationError:
        pass


def test_run_file_write_line_ranges():
    async def _run() -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.txt"
            path.write_text("L1\nL2\nL3\nL4\nL5\n", encoding="utf-8")

            # mid replace: lines 2-4 → NEW
            out = await run_file_write(
                FileWriteAction(path=str(path), content="N2\nN3", start_line=2, end_line=4)
            )
            assert out.exit_code == 0
            assert path.read_text(encoding="utf-8") == "L1\nN2\nN3\nL5\n"

            # only end_line: replace first 2 lines
            path.write_text("A\nB\nC\nD\n", encoding="utf-8")
            out = await run_file_write(FileWriteAction(path=str(path), content="X", end_line=2))
            assert out.exit_code == 0
            assert path.read_text(encoding="utf-8") == "X\nC\nD\n"

            # only start_line: replace from 3 to EOF
            path.write_text("A\nB\nC\nD\n", encoding="utf-8")
            out = await run_file_write(FileWriteAction(path=str(path), content="Z1\nZ2", start_line=3))
            assert out.exit_code == 0
            assert path.read_text(encoding="utf-8") == "A\nB\nZ1\nZ2\n"

            # start past EOF → append
            path.write_text("A\nB\n", encoding="utf-8")
            out = await run_file_write(
                FileWriteAction(path=str(path), content="TAIL", start_line=100, end_line=200)
            )
            assert out.exit_code == 0
            assert path.read_text(encoding="utf-8") == "A\nB\nTAIL\n"

            # empty content deletes the range
            path.write_text("A\nB\nC\nD\n", encoding="utf-8")
            out = await run_file_write(
                FileWriteAction(path=str(path), content="", start_line=2, end_line=3)
            )
            assert out.exit_code == 0
            assert path.read_text(encoding="utf-8") == "A\nD\n"

            # no range → full overwrite (unchanged behavior)
            out = await run_file_write(FileWriteAction(path=str(path), content="FULL\n"))
            assert out.exit_code == 0
            assert path.read_text(encoding="utf-8") == "FULL\n"

    asyncio.run(_run())
