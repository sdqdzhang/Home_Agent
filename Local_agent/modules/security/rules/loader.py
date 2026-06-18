from __future__ import annotations

from pathlib import Path

from modules.security.config import security_settings


def _read_list_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    items: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        items.append(text)
    return items


def load_white_commands() -> list[str]:
    return _read_list_file(security_settings.white_commands_file)


def load_black_commands() -> list[str]:
    return _read_list_file(security_settings.black_commands_file)


def load_white_directories() -> list[str]:
    return _read_list_file(security_settings.white_directories_file)


def load_black_directories() -> list[str]:
    return _read_list_file(security_settings.black_directories_file)


def reload_lists() -> dict[str, list[str]]:
    return {
        "white_commands": load_white_commands(),
        "black_commands": load_black_commands(),
        "white_directories": load_white_directories(),
        "black_directories": load_black_directories(),
    }
