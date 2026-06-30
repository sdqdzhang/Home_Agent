from __future__ import annotations

from pathlib import Path

from modules.security.config import security_settings

LIST_KEYS = frozenset(
    {
        "white_commands",
        "black_commands",
        "white_directories",
        "black_directories",
    }
)

_LIST_FILES: dict[str, Path] = {
    "white_commands": security_settings.white_commands_file,
    "black_commands": security_settings.black_commands_file,
    "white_directories": security_settings.white_directories_file,
    "black_directories": security_settings.black_directories_file,
}


def _read_header_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    header: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            header.append(line)
        else:
            break
    return header


def _normalize_items(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in items:
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def read_list_items(list_key: str) -> list[str]:
    path = _LIST_FILES.get(list_key)
    if path is None:
        raise ValueError(f"未知列表: {list_key}")
    if not path.exists():
        return []
    items: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        items.append(text)
    return items


def write_list_items(list_key: str, items: list[str]) -> list[str]:
    path = _LIST_FILES.get(list_key)
    if path is None:
        raise ValueError(f"未知列表: {list_key}")

    normalized = _normalize_items(items)
    header = _read_header_lines(path)
    lines = list(header)
    if lines and lines[-1].strip():
        lines.append("")
    lines.extend(normalized)
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return normalized


def snapshot_lists() -> dict[str, list[str]]:
    return {key: read_list_items(key) for key in sorted(LIST_KEYS)}
