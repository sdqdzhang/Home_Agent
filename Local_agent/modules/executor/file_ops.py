from __future__ import annotations

import fnmatch
import time
from pathlib import Path

from modules.executor.runner import RunOutput, resolve_path


def format_directory_tree(root: Path, *, max_depth: int = 4) -> str:
    if not root.exists():
        return f"路径不存在: {root}"
    if not root.is_dir():
        return f"不是目录: {root}"

    lines: list[str] = [str(root)]
    _walk_tree(root, prefix="", depth=0, max_depth=max_depth, lines=lines)
    return "\n".join(lines)


def _walk_tree(path: Path, *, prefix: str, depth: int, max_depth: int, lines: list[str]) -> None:
    if depth >= max_depth:
        return
    try:
        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError as exc:
        lines.append(f"{prefix}└── [无法读取: {exc}]")
        return

    for index, entry in enumerate(entries):
        is_last = index == len(entries) - 1
        branch = "└── " if is_last else "├── "
        lines.append(f"{prefix}{branch}{entry.name}{'/' if entry.is_dir() else ''}")
        if entry.is_dir():
            extension = "    " if is_last else "│   "
            _walk_tree(entry, prefix=prefix + extension, depth=depth + 1, max_depth=max_depth, lines=lines)


def search_files_by_name(pattern: str, root: Path, *, limit: int = 200) -> list[str]:
    if not root.exists():
        raise FileNotFoundError(f"目录不存在: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"不是目录: {root}")

    pattern = pattern.strip().replace("\\", "/").lstrip("./")
    if not pattern:
        return []

    found: list[str] = []
    seen: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        name = path.name
        rel = str(path.relative_to(root)).replace("\\", "/")
        matched = (
            name == pattern
            or fnmatch.fnmatch(name, pattern)
            or fnmatch.fnmatch(rel, pattern)
            or (not any(ch in pattern for ch in "*?[]") and pattern.lower() in name.lower())
        )
        if not matched:
            continue
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        found.append(key)
        if len(found) >= limit:
            break
    return sorted(found)


def search_content_in_file(path: Path, query: str, *, context_lines: int = 5) -> str:
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    query = query.strip()
    if not query:
        return ""

    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    hits: list[tuple[int, list[str]]] = []

    for index, line in enumerate(lines, start=1):
        if query not in line:
            continue
        start = max(1, index - context_lines)
        end = min(len(lines), index + context_lines)
        snippet: list[str] = []
        for line_no in range(start, end + 1):
            marker = ">" if line_no == index else " "
            snippet.append(f"{marker} {line_no:4d}| {lines[line_no - 1]}")
        hits.append((index, snippet))

    if not hits:
        return f"未在 {path} 中找到: {query!r}"

    parts: list[str] = [f"=== {path} ({len(hits)} 处匹配) ==="]
    for line_no, snippet in hits:
        parts.append(f"--- 行 {line_no} ---")
        parts.extend(snippet)
        parts.append("")
    return "\n".join(parts).rstrip()


async def run_dir_browse(path: str | None, *, max_depth: int = 4, on_line=None) -> RunOutput:
    started = time.perf_counter()
    root = resolve_path(path) if path else resolve_path(".")
    if on_line:
        on_line(f"dir.browse: {root} (depth={max_depth})")
    tree = format_directory_tree(root, max_depth=max_depth)
    duration_ms = int((time.perf_counter() - started) * 1000)
    return RunOutput(exit_code=0, stdout=tree, stderr="", duration_ms=duration_ms)


async def run_file_search(pattern: str, root: str | None, *, on_line=None) -> RunOutput:
    started = time.perf_counter()
    base = resolve_path(root) if root else resolve_path(".")
    if on_line:
        on_line(f"file.search: pattern={pattern!r} root={base}")
    try:
        matches = search_files_by_name(pattern, base)
    except (FileNotFoundError, NotADirectoryError) as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return RunOutput(exit_code=1, stdout="", stderr=str(exc), duration_ms=duration_ms)

    stdout = "\n".join(matches) if matches else f"未找到匹配 {pattern!r} 的文件（搜索根: {base}）"
    duration_ms = int((time.perf_counter() - started) * 1000)
    if on_line:
        on_line(f"found {len(matches)} file(s)")
    return RunOutput(exit_code=0, stdout=stdout, stderr="", duration_ms=duration_ms)


async def run_content_search(path: str, query: str, *, context_lines: int = 5, on_line=None) -> RunOutput:
    started = time.perf_counter()
    file_path = resolve_path(path)
    if on_line:
        on_line(f"content.search: {file_path} query={query!r}")
    try:
        stdout = search_content_in_file(file_path, query, context_lines=context_lines)
    except FileNotFoundError as exc:
        duration_ms = int((time.perf_counter() - started) * 1000)
        return RunOutput(exit_code=1, stdout="", stderr=str(exc), duration_ms=duration_ms)

    duration_ms = int((time.perf_counter() - started) * 1000)
    return RunOutput(exit_code=0, stdout=stdout, stderr="", duration_ms=duration_ms)


async def run_file_delete(path: str, *, on_line=None) -> RunOutput:
    started = time.perf_counter()
    file_path = resolve_path(path)
    if on_line:
        on_line(f"file.delete: {file_path}")
    if not file_path.exists():
        duration_ms = int((time.perf_counter() - started) * 1000)
        return RunOutput(exit_code=1, stdout="", stderr=f"文件不存在: {file_path}", duration_ms=duration_ms)
    if file_path.is_dir():
        duration_ms = int((time.perf_counter() - started) * 1000)
        return RunOutput(exit_code=1, stdout="", stderr=f"目标是目录，请使用专用删除目录能力: {file_path}", duration_ms=duration_ms)

    file_path.unlink()
    duration_ms = int((time.perf_counter() - started) * 1000)
    if on_line:
        on_line(f"deleted {file_path}")
    return RunOutput(exit_code=0, stdout="", stderr="", duration_ms=duration_ms, files_touched=[str(file_path)])
