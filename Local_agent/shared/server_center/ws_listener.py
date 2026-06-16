from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urlparse

import websockets

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict[str, Any]], Awaitable[None]]


class WebSocketListener:
    """监听 Server Center WebSocket，接收发往本模块的消息与回复。"""

    def __init__(self, server_center_url: str, channel: str) -> None:
        parsed = urlparse(server_center_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if scheme == "wss" else 80)
        self.ws_url = f"{scheme}://{host}:{port}/ws/{channel}"
        self.channel = channel
        self._handlers: list[MessageHandler] = []
        self._task: asyncio.Task[None] | None = None

    def on_message(self, handler: MessageHandler) -> None:
        self._handlers.append(handler)

    async def start(self) -> None:
        if self._task and not self._task.done():
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

    async def _run_loop(self) -> None:
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    logger.info("WebSocket connected: %s", self.ws_url)
                    async for raw in ws:
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        await self._dispatch(event)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("WebSocket disconnected (%s), reconnecting in 5s", exc)
                await asyncio.sleep(5)

    async def _dispatch(self, event: dict[str, Any]) -> None:
        event_type = event.get("event")
        if event_type not in ("new_message", "message_updated", "response_ready"):
            return
        data = event.get("data")
        if not isinstance(data, dict):
            return
        for handler in self._handlers:
            try:
                await handler(data)
            except Exception:
                logger.exception("WebSocket handler error")
