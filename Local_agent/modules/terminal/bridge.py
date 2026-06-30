from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from urllib.parse import urlparse

import websockets

from app.config import settings
from modules.terminal.config import terminal_settings
from modules.terminal.pty_session import PtySession

logger = logging.getLogger(__name__)


class TerminalBridge:
    """连接 Server Center /ws/terminal_agent，在收到 session_start 时拉起本机 PTY。"""

    def __init__(self) -> None:
        self._task: asyncio.Task[None] | None = None
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._session: PtySession | None = None
        self._send_lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def _ws_url(self) -> str:
        parsed = urlparse(settings.server_center_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if scheme == "wss" else 80)
        return f"{scheme}://{host}:{port}/ws/terminal_agent"

    async def start(self) -> None:
        if not terminal_settings.enabled:
            logger.info("Terminal bridge disabled (LA_TERMINAL_ENABLED=false)")
            return
        if self.running:
            return
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._close_session()
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def _run_loop(self) -> None:
        while True:
            try:
                async with websockets.connect(self._ws_url(), max_size=2**20) as ws:
                    self._ws = ws
                    logger.info("Terminal bridge connected: %s", self._ws_url())
                    await ws.send(json.dumps({"type": "agent_hello"}, ensure_ascii=False))
                    async for raw in ws:
                        if isinstance(raw, bytes):
                            if self._session:
                                await self._session.write(raw)
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        await self._handle_control(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Terminal bridge disconnected (%s), reconnecting in 5s", exc)
                await self._close_session()
                await asyncio.sleep(5)

    async def _handle_control(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        if event_type == "session_start":
            await self._start_session(
                cols=int(event.get("cols") or 120),
                rows=int(event.get("rows") or 30),
            )
            return
        if event_type == "session_end":
            await self._close_session()
            return
        if event_type == "resize" and self._session:
            await self._session.resize(
                cols=int(event.get("cols") or 120),
                rows=int(event.get("rows") or 30),
            )

    async def _start_session(self, *, cols: int, rows: int) -> None:
        await self._close_session()
        session = PtySession()

        async def on_output(data: bytes) -> None:
            await self._send_bytes(data)

        try:
            await session.start(cols=cols, rows=rows, on_output=on_output)
        except Exception as exc:
            logger.exception("Failed to start PTY session")
            await self._send_json({"type": "error", "message": str(exc)})
            return

        self._session = session
        await self._send_json({"type": "session_ready"})

    async def _close_session(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def _send_bytes(self, data: bytes) -> None:
        ws = self._ws
        if ws is None:
            return
        async with self._send_lock:
            try:
                await ws.send(data)
            except Exception:
                logger.exception("Terminal bridge send failed")

    async def _send_json(self, payload: dict[str, Any]) -> None:
        ws = self._ws
        if ws is None:
            return
        async with self._send_lock:
            try:
                await ws.send(json.dumps(payload, ensure_ascii=False))
            except Exception:
                logger.exception("Terminal bridge send failed")
