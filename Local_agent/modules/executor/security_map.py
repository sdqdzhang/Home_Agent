from __future__ import annotations

from modules.executor.schemas import (
    ContentSearchAction,
    DirBrowseAction,
    FileDeleteAction,
    FileReadAction,
    FileSearchAction,
    FileWriteAction,
    ShellRunAction,
)


def security_command_for_action(
    action: ShellRunAction
    | FileReadAction
    | FileWriteAction
    | FileDeleteAction
    | DirBrowseAction
    | FileSearchAction
    | ContentSearchAction,
) -> str:
    if isinstance(action, ShellRunAction):
        return action.command
    if isinstance(action, FileReadAction):
        return f"executor:file.read {action.path}"
    if isinstance(action, FileWriteAction):
        return f"executor:file.write {action.path}"
    if isinstance(action, FileDeleteAction):
        return f"executor:file.delete {action.path}"
    if isinstance(action, DirBrowseAction):
        path = action.path or "."
        return f"executor:dir.browse {path}"
    if isinstance(action, FileSearchAction):
        root = action.root or "."
        return f"executor:file.search {root} {action.pattern}"
    return f"executor:content.search {action.path}"
