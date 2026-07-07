from __future__ import annotations

import tempfile
from pathlib import Path

from modules.executor.capabilities import CAPABILITIES, EXECUTOR_MODES
from modules.executor.file_ops import format_directory_tree, search_content_in_file, search_files_by_name
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
