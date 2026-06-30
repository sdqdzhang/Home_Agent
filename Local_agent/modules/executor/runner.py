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


@dataclass
class RunOutput:
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    files_touched: list[str] = field(default_factory=list)


def security_command_for_action(action: ShellRunAction | FileReadAction | FileWriteAction) -> str:
    if isinstance(action, ShellRunAction):
        return action.command
    if isinstance(action, FileReadAction):
        return f"executor:file.read {action.path}"
    return f"executor:file.write {action.path}"


def resolve_cwd(cwd: str | None) -> Path:
    if cwd:
        return Path(cwd).expanduser().resolve()
    return executor_settings.default_cwd.resolve()


def resolve_path(path: str) -> Path:
    p = Path(path).expanduser()
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

    stdout = stdout_b.decode("utf-8", errors="replace")
    stderr = stderr_b.decode("utf-8", errors="replace")
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

    content = path.read_text(encoding=action.encoding, errors="replace")
    duration_ms = int((time.perf_counter() - started) * 1000)
    if on_line:
        on_line(f"read {len(content)} chars")
    return RunOutput(exit_code=0, stdout=content, stderr="", duration_ms=duration_ms, files_touched=[str(path)])


async def run_file_write(action: FileWriteAction, *, on_line: Callable[[str], None] | None = None) -> RunOutput:
    started = time.perf_counter()
    path = resolve_path(action.path)
    if on_line:
        on_line(f"file.write: {path}")

    path.parent.mkdir(parents=True, exist_ok=True)
    existed = path.exists()
    path.write_text(action.content if action.content is not None else "", encoding=action.encoding)
    duration_ms = int((time.perf_counter() - started) * 1000)
    if on_line:
        on_line(f"{'updated' if existed else 'created'} {path}")
    return RunOutput(exit_code=0, stdout="", stderr="", duration_ms=duration_ms, files_touched=[str(path)])


async def run_action(
    action: ShellRunAction | FileReadAction | FileWriteAction,
    *,
    on_line: Callable[[str], None] | None = None,
    run_ctx: dict | None = None,
) -> RunOutput:
    if isinstance(action, ShellRunAction):
        return await run_shell(action, on_line=on_line, run_ctx=run_ctx)
    if isinstance(action, FileReadAction):
        return await run_file_read(action, on_line=on_line)
    return await run_file_write(action, on_line=on_line)


def output_to_result(
    job_id: str,
    action: ShellRunAction | FileReadAction | FileWriteAction,
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
