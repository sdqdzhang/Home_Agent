from __future__ import annotations

from pathlib import Path

_TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".json",
    ".csv",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".xml",
    ".yaml",
    ".yml",
}


def load_file_text(path: str | Path) -> tuple[str, str]:
    file_path = Path(path).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix not in _TEXT_SUFFIXES:
        raise ValueError(f"不支持的文件类型: {suffix}，当前仅支持文本类文件")

    content = file_path.read_text(encoding="utf-8", errors="replace")
    title = file_path.name
    return content, title
