from __future__ import annotations

import re
from pathlib import Path

from modules.security.rules.loader import load_black_directories, load_white_directories

_PATH_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\\/][^\s\"'|&;]+)|(?:~[/\\][^\s\"'|&;]+)|(?:[/\\][^\s\"'|&;]+)|(?:[A-Za-z0-9_.-]+[/\\][A-Za-z0-9_./\\-]+)"
)


def _normalize_path(path: str) -> str:
    text = path.strip().strip("\"'")
    text = text.replace("\\", "/")
    if text.startswith("~/"):
        home = Path.home().as_posix()
        text = f"{home}/{text[2:]}"
    return text


def extract_paths(command: str) -> list[str]:
    found: list[str] = []
    for match in _PATH_PATTERN.findall(command):
        normalized = _normalize_path(match)
        if normalized and normalized not in found:
            found.append(normalized)
    return found


def _path_matches_prefix(path: str, prefix: str) -> bool:
    norm_path = _normalize_path(path)
    norm_prefix = _normalize_path(prefix)
    if not norm_prefix:
        return False
    if not norm_prefix.endswith("/"):
        norm_prefix = f"{norm_prefix}/"
    if norm_path == norm_prefix.rstrip("/"):
        return True
    if not norm_path.endswith("/"):
        norm_path = f"{norm_path}/"
    return norm_path.startswith(norm_prefix) or norm_path == norm_prefix.rstrip("/")


def paths_in_list(paths: list[str], entries: list[str]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        for entry in entries:
            if _path_matches_prefix(path, entry):
                hits.append(path)
                break
    return hits


def only_white_directories(paths: list[str]) -> bool:
    if not paths:
        return True
    white = load_white_directories()
    for path in paths:
        if not any(_path_matches_prefix(path, entry) for entry in white):
            return False
    return True


def find_black_directories(paths: list[str]) -> list[str]:
    return paths_in_list(paths, load_black_directories())
