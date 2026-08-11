from __future__ import annotations

import asyncio
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from modules.executor.config import executor_settings
from modules.executor.schemas import (
    ExecuteResult,
    FileReadAction,
    FileWriteAction,
    SecurityInfo,
    ShellRunAction,
)
from typing import Any


@dataclass
class RunOutput:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    files_touched: list[str] = field(default_factory=list)


def decode_subprocess_output(data: bytes) -> str:
    """解码子进程输出：优先 UTF-8，失败再回退 GBK（中文 Windows 控制台常见）。"""
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("gbk", errors="replace")


def resolve_cwd(cwd: str | None) -> Path:
    if cwd:
        return Path(cwd).expanduser().resolve()
    return executor_settings.default_cwd.resolve()


def _normalize_path_text(path: str) -> str:
    text = path.strip().strip('"').strip("'")
    if not text:
        return text
    # 模型偶发输出 JSON 风格的多重反斜杠，收敛为单分隔符
    if "\\" in text:
        parts = [part for part in text.replace("/", "\\").split("\\") if part != ""]
        if len(parts) >= 2 and parts[0].endswith(":"):
            return "\\".join(parts)
    return text


def resolve_path(path: str) -> Path:
    p = Path(_normalize_path_text(path)).expanduser()
    if p.is_absolute():
        return p.resolve()
    return (executor_settings.default_cwd / p).resolve()


def _kill_process_tree(proc: subprocess.Popen[bytes]) -> None:
    """终止进程；Windows 上连同子进程（如 powershell 下的 python.exe）一并结束。"""
    if proc.poll() is not None:
        return
    if sys.platform == "win32" and proc.pid:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=10,
                check=False,
            )
            return
        except Exception:
            pass
    proc.kill()


def _run_shell_sync(
    *,
    argv: list[str] | None,
    shell_command: str | None,
    cwd: str,
    timeout: int,
    run_ctx: dict | None = None,
) -> tuple[int, bytes, bytes]:
    """同步子进程执行（在线程池中调用，规避 Windows asyncio 子进程限制）。"""
    if run_ctx and run_ctx.get("cancelled"):
        return -1, b"", "用户已终止执行".encode("utf-8")

    proc: subprocess.Popen[bytes] | None = None
    try:
        if argv is not None:
            proc = subprocess.Popen(
                argv,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        else:
            proc = subprocess.Popen(
                shell_command,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
            )

        if run_ctx is not None:
            run_ctx["proc"] = proc

        if run_ctx and run_ctx.get("cancelled"):
            _kill_process_tree(proc)
            stdout, stderr = proc.communicate()
            return -1, stdout or b"", (stderr or b"") + "\n用户已终止执行".encode("utf-8")

        stdout, stderr = proc.communicate(timeout=timeout)
        if run_ctx and run_ctx.get("cancelled"):
            _kill_process_tree(proc)
            stdout, stderr = proc.communicate()
            return -1, stdout or b"", (stderr or b"") + "\n用户已终止执行".encode("utf-8")
        return proc.returncode, stdout, stderr
    except subprocess.TimeoutExpired as exc:
        if proc is not None:
            _kill_process_tree(proc)
            stdout, stderr = proc.communicate()
        else:
            stdout, stderr = exc.stdout or b"", exc.stderr or b""
        stderr = stderr + f"\n命令超时（>{timeout}s）".encode("utf-8")
        return -1, stdout, stderr
    except Exception as exc:
        if proc is not None and proc.poll() is None:
            _kill_process_tree(proc)
        return -1, b"", str(exc).encode("utf-8")


async def run_shell(
    action: ShellRunAction,
    *,
    on_line: Callable[[str], None] | None = None,
    run_ctx: dict | None = None,
) -> RunOutput:
    cwd = resolve_cwd(action.cwd)
    timeout = action.timeout_seconds or executor_settings.timeout_seconds
    started = time.perf_counter()

    if on_line:
        on_line(f"shell: {executor_settings.shell}")
        on_line(f"cwd: {cwd}")
        on_line(f"command: {action.command}")

    if executor_settings.shell.lower() == "powershell":
        argv = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            action.command,
        ]
        exit_code, stdout_b, stderr_b = await asyncio.to_thread(
            _run_shell_sync,
            argv=argv,
            shell_command=None,
            cwd=str(cwd),
            timeout=timeout,
            run_ctx=run_ctx,
        )
    else:
        exit_code, stdout_b, stderr_b = await asyncio.to_thread(
            _run_shell_sync,
            argv=None,
            shell_command=action.command,
            cwd=str(cwd),
            timeout=timeout,
            run_ctx=run_ctx,
        )

    stdout = decode_subprocess_output(stdout_b)
    stderr = decode_subprocess_output(stderr_b)
    duration_ms = int((time.perf_counter() - started) * 1000)

    if on_line:
        if stdout:
            on_line(f"stdout:\n{stdout.rstrip()}")
        if stderr:
            on_line(f"stderr:\n{stderr.rstrip()}")
        on_line(f"exit_code: {exit_code}")

    return RunOutput(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        duration_ms=duration_ms,
    )


async def run_file_read(action: FileReadAction, *, on_line: Callable[[str], None] | None = None) -> RunOutput:
    started = time.perf_counter()
    path = resolve_path(action.path)
    if on_line:
        on_line(f"file.read: {path}")

    if not path.is_file():
        duration_ms = int((time.perf_counter() - started) * 1000)
        return RunOutput(exit_code=1, stdout="", stderr=f"文件不存在: {path}", duration_ms=duration_ms)

    has_range = action.start_line is not None or action.end_line is not None
    if not has_range:
        content = path.read_text(encoding=action.encoding, errors="replace")
        duration_ms = int((time.perf_counter() - started) * 1000)
        if on_line:
            on_line(f"read {len(content)} chars")
        return RunOutput(exit_code=0, stdout=content, stderr="", duration_ms=duration_ms, files_touched=[str(path)])

    start_y = action.start_line if action.start_line is not None else 1
    end_z = action.end_line  # None → EOF
    selected: list[str] = []
    total_lines = 0
    with path.open("r", encoding=action.encoding, errors="replace", newline="") as fh:
        for line_no, line in enumerate(fh, start=1):
            if end_z is not None and line_no > end_z:
                break
            total_lines = line_no
            if line_no < start_y:
                continue
            selected.append(line.rstrip("\r\n"))

    content = "\n".join(selected)
    duration_ms = int((time.perf_counter() - started) * 1000)
    if on_line:
        if not selected:
            on_line(f"read lines (empty intersection; file has {total_lines} lines)")
        else:
            actual_start = start_y
            actual_end = start_y + len(selected) - 1
            on_line(f"read lines {actual_start}-{actual_end} of {total_lines} ({len(content)} chars)")
    return RunOutput(exit_code=0, stdout=content, stderr="", duration_ms=duration_ms, files_touched=[str(path)])


def _apply_line_range_write(existing: str, replacement: str, *, start_line: int | None, end_line: int | None) -> tuple[str, str]:
    """Replace lines in [start_line, end_line] ∩ [1, X] with replacement lines.

    Returns (new_text, log_detail).
    Empty intersection (start > X): append replacement after existing lines.
    """
    lines = existing.splitlines()
    total = len(lines)
    start_y = start_line if start_line is not None else 1
    end_z = end_line if end_line is not None else total
    new_lines = replacement.splitlines() if replacement else []

    if total == 0 or start_y > total:
        # Empty file or start past EOF → append
        merged = lines + new_lines
        text = "\n".join(merged)
        if merged:
            text += "\n"
        detail = f"append after line {total} ({len(new_lines)} new lines; file had {total} lines)"
        return text, detail

    actual_start = start_y
    actual_end = min(end_z, total)
    # 1-based inclusive → slice [actual_start-1 : actual_end]
    prefix = lines[: actual_start - 1]
    suffix = lines[actual_end:]
    merged = prefix + new_lines + suffix
    text = "\n".join(merged)
    if merged:
        text += "\n"
    detail = (
        f"replace lines {actual_start}-{actual_end} of {total} "
        f"with {len(new_lines)} line(s)"
    )
    return text, detail


async def run_file_write(action: FileWriteAction, *, on_line: Callable[[str], None] | None = None) -> RunOutput:
    started = time.perf_counter()
    path = resolve_path(action.path)
    if on_line:
        on_line(f"file.write: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    body = action.content if action.content is not None else ""
    has_range = action.start_line is not None or action.end_line is not None

    if not has_range:
        path.write_text(body, encoding=action.encoding)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if on_line:
            on_line(f"{'updated' if existed else 'created'} {path}")
        return RunOutput(exit_code=0, stdout="", stderr="", duration_ms=duration_ms, files_touched=[str(path)])

    existing = ""
    if existed and path.is_file():
        existing = path.read_text(encoding=action.encoding, errors="replace")
    elif existed and path.is_dir():
        duration_ms = int((time.perf_counter() - started) * 1000)
        return RunOutput(
            exit_code=1,
            stdout="",
            stderr=f"目标是目录，无法按行写入: {path}",
            duration_ms=duration_ms,
        )

    text, detail = _apply_line_range_write(
        existing,
        body,
        start_line=action.start_line,
        end_line=action.end_line,
    )
    path.write_text(text, encoding=action.encoding)
    duration_ms = int((time.perf_counter() - started) * 1000)
    if on_line:
        on_line(detail)
        on_line(f"{'updated' if existed else 'created'} {path}")
    return RunOutput(exit_code=0, stdout="", stderr="", duration_ms=duration_ms, files_touched=[str(path)])


async def run_action(
    action: Any,
    *,
    on_line: Callable[[str], None] | None = None,
    run_ctx: dict | None = None,
) -> RunOutput:
    if isinstance(action, ShellRunAction):
        return await run_shell(action, on_line=on_line, run_ctx=run_ctx)
    if isinstance(action, FileReadAction):
        return await run_file_read(action, on_line=on_line)
    if isinstance(action, FileWriteAction):
        return await run_file_write(action, on_line=on_line)
    raise TypeError(f"unsupported action for run_action: {type(action)}")


def output_to_result(
    job_id: str,
    action: Any,
    output: RunOutput,
    *,
    security: SecurityInfo | None = None,
) -> ExecuteResult:
    ok = output.exit_code == 0
    return ExecuteResult(
        ok=ok,
        job_id=job_id,
        error=None if ok else "execution_failed",
        reason="" if ok else (output.stderr or f"exit_code={output.exit_code}"),
        action_type=action.type,
        exit_code=output.exit_code,
        stdout=output.stdout,
        stderr=output.stderr,
        duration_ms=output.duration_ms,
        files_touched=output.files_touched,
        security=security,
        parsed_action=action.model_dump(),
    )
