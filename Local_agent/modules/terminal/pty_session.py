from __future__ import annotations

import asyncio
import logging
import os
import struct
import sys
from collections.abc import Awaitable, Callable

if sys.platform != "win32":
    import fcntl
    import termios
from pathlib import Path

from modules.terminal.config import terminal_settings

logger = logging.getLogger(__name__)

OnOutput = Callable[[bytes], Awaitable[None]]


class PtySession:
    """交互式 PTY 会话；Windows 用 ConPTY，Unix 用 openpty。"""

    def __init__(self) -> None:
        self._closed = False
        self._read_task: asyncio.Task[None] | None = None
        self._pty = None
        self._master_fd: int | None = None
        self._proc: asyncio.subprocess.Process | None = None

    @property
    def alive(self) -> bool:
        if self._closed:
            return False
        if sys.platform == "win32":
            return self._pty is not None and self._pty.isalive()
        return self._proc is not None and self._proc.returncode is None

    def _resolve_cwd(self) -> str:
        if terminal_settings.default_cwd:
            return str(terminal_settings.default_cwd.expanduser().resolve())
        return str(Path.cwd())

    def _shell_argv(self) -> list[str]:
        shell = terminal_settings.shell.lower()
        if shell in ("cmd", "cmd.exe"):
            return ["cmd.exe"]
        if shell in ("powershell", "powershell.exe", "pwsh"):
            return ["powershell.exe", "-NoLogo"]
        return [terminal_settings.shell]

    async def start(self, *, cols: int, rows: int, on_output: OnOutput) -> None:
        if sys.platform == "win32":
            await self._start_windows(cols=cols, rows=rows, on_output=on_output)
        else:
            await self._start_unix(cols=cols, rows=rows, on_output=on_output)

    async def _start_windows(self, *, cols: int, rows: int, on_output: OnOutput) -> None:
        PtyProcess = _load_win_pty_process()

        cwd = self._resolve_cwd()
        argv = self._shell_argv()
        command = argv[0] if len(argv) == 1 else " ".join(argv)
        self._pty = PtyProcess.spawn(
            command,
            cwd=cwd,
            dimensions=(rows, cols),
        )
        self._read_task = asyncio.create_task(self._read_windows(on_output))

    async def _read_windows(self, on_output: OnOutput) -> None:
        assert self._pty is not None
        while not self._closed and self._pty.isalive():
            try:
                chunk = await asyncio.to_thread(self._pty.read, 4096)
            except EOFError:
                break
            except Exception:
                logger.exception("PTY read error")
                break
            if not chunk:
                await asyncio.sleep(0.02)
                continue
            data = chunk.encode("utf-8", errors="replace") if isinstance(chunk, str) else chunk
            await on_output(data)
        if not self._closed:
            await on_output(b"\r\n[session ended]\r\n")

    async def _start_unix(self, *, cols: int, rows: int, on_output: OnOutput) -> None:
        master_fd, slave_fd = os.openpty()
        self._set_winsize(master_fd, rows, cols)
        argv = self._shell_argv()
        self._proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=self._resolve_cwd(),
            start_new_session=True,
        )
        os.close(slave_fd)
        self._master_fd = master_fd
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
        self._read_task = asyncio.create_task(self._read_unix(on_output))

    async def _read_unix(self, on_output: OnOutput) -> None:
        assert self._master_fd is not None
        while not self._closed:
            try:
                chunk = os.read(self._master_fd, 4096)
            except BlockingIOError:
                if self._proc and self._proc.returncode is not None:
                    break
                await asyncio.sleep(0.02)
                continue
            except OSError:
                break
            if not chunk:
                if self._proc and self._proc.returncode is not None:
                    break
                await asyncio.sleep(0.02)
                continue
            await on_output(chunk)
        if not self._closed:
            await on_output(b"\n[session ended]\n")

    async def write(self, data: bytes) -> None:
        if self._closed:
            return
        if sys.platform == "win32":
            if self._pty is None:
                return
            text = data.decode("utf-8", errors="replace")
            await asyncio.to_thread(self._pty.write, text)
            return
        if self._master_fd is None:
            return
        os.write(self._master_fd, data)

    async def resize(self, cols: int, rows: int) -> None:
        if self._closed:
            return
        cols = max(cols, 2)
        rows = max(rows, 2)
        if sys.platform == "win32":
            if self._pty is not None:
                await asyncio.to_thread(self._pty.setwinsize, rows, cols)
            return
        if self._master_fd is not None:
            self._set_winsize(self._master_fd, rows, cols)

    async def close(self) -> None:
        self._closed = True
        if self._read_task and not self._read_task.done():
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
        if sys.platform == "win32":
            if self._pty is not None:
                try:
                    if self._pty.isalive():
                        await asyncio.to_thread(self._pty.terminate, force=True)
                except Exception:
                    logger.exception("Failed to terminate PTY")
            self._pty = None
            return
        if self._master_fd is not None:
            try:
                os.close(self._master_fd)
            except OSError:
                pass
            self._master_fd = None
        if self._proc and self._proc.returncode is None:
            self._proc.kill()
            await self._proc.wait()

    @staticmethod
    def _set_winsize(fd: int, rows: int, cols: int) -> None:
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


def _load_win_pty_process():
    """pywinpty 3.x 导出为 winpty；旧版为 pywinpty。"""
    try:
        from winpty import PtyProcess

        return PtyProcess
    except ImportError:
        pass
    try:
        from pywinpty import PtyProcess

        return PtyProcess
    except ImportError as exc:
        raise RuntimeError("终端需要 pywinpty，请在 Local_agent venv 中执行: pip install pywinpty") from exc
