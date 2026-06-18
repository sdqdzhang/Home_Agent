from __future__ import annotations

import re
import shlex
from pathlib import Path

from modules.security.rules.loader import load_black_commands, load_white_commands

_CMD_SPLIT = re.compile(r"[\s|&;]+")
_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'|&;]+)|(?:~[/\\][^\s\"'|&;]+)|(?:[/\\][^\s\"'|&;]+)|(?:[A-Za-z0-9_.-]+[/\\][A-Za-z0-9_./\\-]+)"
)


def command_verb(command: str) -> str:
    text = command.strip()
    if not text:
        return ""
    try:
        parts = shlex.split(text, posix=False)
        return parts[0] if parts else ""
    except ValueError:
        parts = _CMD_SPLIT.split(text, maxsplit=1)
        return parts[0] if parts else ""


def _normalize_token(token: str) -> str:
    return token.strip().strip("\"'").lower()


def matches_command_list(command: str, entries: list[str]) -> bool:
    verb = _normalize_token(command_verb(command))
    if not verb:
        return False
    normalized = {_normalize_token(item) for item in entries}
    return verb in normalized


def is_white_command(command: str) -> bool:
    return matches_command_list(command, load_white_commands())


def is_black_command(command: str) -> bool:
    return matches_command_list(command, load_black_commands())
