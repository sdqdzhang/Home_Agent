from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.config import settings

logger = logging.getLogger(__name__)

TERMINAL_CLIENT_ID = "terminal"


class TerminalRelay:
    """在浏览器 UI 与 Local Agent 终端桥之间转发 PTY 数据。"""

    def __init__(self) -> None:
        self._agent: WebSocket | None = None
        self._ui: WebSocket | None = None
        self._lock = asyncio.Lock()
        self._ui_send_lock = asyncio.Lock()
        self._agent_send_lock = asyncio.Lock()
        self._ui_session_id = 0

    @property
    def agent_connected(self) -> bool:
        return self._agent is not None

    def _encrypt_for_agent(self, data: bytes) -> dict[str, Any] | None:
        from app.crypto.rsa import encrypt_payload_b64, load_public_key_from_pem
        from app.services.message_service import message_service

        pem = message_service.get_client_public_key(TERMINAL_CLIENT_ID)
        if not pem:
            return None
        return encrypt_payload_b64(data, load_public_key_from_pem(pem))

    def _decrypt_from_agent(self, payload: dict[str, Any]) -> bytes:
        from app.crypto.rsa import decrypt_payload_b64
        from app.main import server_private_key

        return decrypt_payload_b64(payload, server_private_key)

    async def attach_agent(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._agent = websocket

        try:
            await self._agent_send_control({"type": "registered"})
            if self._ui is not None:
                await self._request_session_start(cols=120, rows=30)
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    if settings.wire_encrypt:
                        logger.warning("Rejecting plaintext terminal binary from agent")
                        continue
                    await self._forward_to_ui_bytes(message["bytes"])
                elif message.get("text"):
                    text = message["text"]
                    await self._handle_agent_text(text)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("terminal_agent handler error")
        finally:
            async with self._lock:
                if self._agent is websocket:
                    self._agent = None
            await self._notify_ui({"type": "agent_disconnected"})

    async def _handle_agent_text(self, text: str) -> None:
        if not text.startswith("{"):
            if settings.wire_encrypt:
                logger.warning("Rejecting plaintext terminal text from agent")
                return
            await self._forward_to_ui_bytes(text.encode("utf-8"))
            return

        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            return

        if settings.wire_encrypt:
            enc = event.get("enc")
            if not isinstance(enc, dict):
                logger.warning("Rejecting plaintext terminal JSON from agent")
                return
            try:
                plain = self._decrypt_from_agent(enc)
            except Exception:
                logger.exception("Failed to decrypt terminal frame from agent")
                return
            if event.get("bin"):
                await self._forward_to_ui_bytes(plain)
                return
            try:
                decoded = plain.decode("utf-8")
            except UnicodeDecodeError:
                await self._forward_to_ui_bytes(plain)
                return
            if decoded.startswith("{"):
                await self._forward_to_ui_text(decoded)
            else:
                await self._forward_to_ui_bytes(plain)
            return

        await self._forward_to_ui_text(text)

    async def attach_ui(self, websocket: WebSocket, *, enabled: bool) -> None:
        await websocket.accept()
        if not enabled:
            await self._ui_send_text(
                json.dumps({"type": "error", "message": "终端功能已关闭（SC_TERMINAL_ENABLED=false）"}, ensure_ascii=False)
            )
            await websocket.close(code=1008)
            return

        async with self._lock:
            self._ui_session_id += 1
            session_id = self._ui_session_id
            self._ui = websocket

        if self._agent is None:
            await self._ui_send_text(
                json.dumps({"type": "error", "message": "Local Agent 未连接，请确认本机 Agent 已启动"}, ensure_ascii=False)
            )
        else:
            await self._request_session_start(cols=120, rows=30)

        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                if message.get("bytes") is not None:
                    await self._forward_to_agent_bytes(message["bytes"])
                elif message.get("text"):
                    text = message["text"]
                    if text.startswith("{"):
                        await self._handle_ui_control(text)
                    else:
                        await self._forward_to_agent_bytes(text.encode("utf-8"))
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("terminal_ui handler error")
        finally:
            should_end = False
            async with self._lock:
                if self._ui is websocket and self._ui_session_id == session_id:
                    self._ui = None
                    should_end = True
            if should_end:
                await self._notify_agent({"type": "session_end"})

    async def _handle_ui_control(self, text: str) -> None:
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            return
        event_type = event.get("type")
        if event_type == "resize":
            await self._notify_agent(
                {
                    "type": "resize",
                    "cols": int(event.get("cols") or 120),
                    "rows": int(event.get("rows") or 30),
                }
            )
            return
        if event_type == "session_start":
            await self._request_session_start(
                cols=int(event.get("cols") or 120),
                rows=int(event.get("rows") or 30),
            )

    async def _request_session_start(self, *, cols: int, rows: int) -> None:
        await self._notify_agent({"type": "session_start", "cols": cols, "rows": rows})

    async def _forward_to_ui_bytes(self, data: bytes) -> None:
        ui = self._ui
        if ui is None:
            return
        try:
            await self._ui_send_bytes(data)
        except Exception:
            logger.exception("Failed to forward terminal output to UI")

    async def _forward_to_ui_text(self, text: str) -> None:
        try:
            await self._ui_send_text(text)
        except Exception:
            logger.exception("Failed to forward terminal control to UI")

    async def _forward_to_agent_bytes(self, data: bytes) -> None:
        if self._agent is None:
            return
        try:
            await self._agent_send_bytes(data)
        except Exception:
            logger.exception("Failed to forward terminal input to agent")

    async def _notify_agent(self, payload: dict[str, Any]) -> None:
        if self._agent is None:
            return
        try:
            await self._agent_send_control(payload)
        except Exception:
            logger.exception("Failed to notify terminal agent")

    async def _notify_ui(self, payload: dict[str, Any]) -> None:
        if self._ui is None:
            return
        try:
            await self._ui_send_text(json.dumps(payload, ensure_ascii=False))
        except Exception:
            logger.exception("Failed to notify terminal UI")

    async def _ui_send_bytes(self, data: bytes) -> None:
        ui = self._ui
        if ui is None:
            return
        async with self._ui_send_lock:
            await ui.send_bytes(data)

    async def _ui_send_text(self, text: str) -> None:
        ui = self._ui
        if ui is None:
            return
        async with self._ui_send_lock:
            await ui.send_text(text)

    async def _agent_send_bytes(self, data: bytes) -> None:
        agent = self._agent
        if agent is None:
            return
        async with self._agent_send_lock:
            if settings.wire_encrypt:
                enc = self._encrypt_for_agent(data)
                if enc is None:
                    logger.error("Refusing plaintext terminal bytes to agent (no terminal client key)")
                    return
                await agent.send_text(json.dumps({"bin": True, "enc": enc}, ensure_ascii=False))
            else:
                await agent.send_bytes(data)

    async def _agent_send_control(self, payload: dict[str, Any]) -> None:
        agent = self._agent
        if agent is None:
            return
        text = json.dumps(payload, ensure_ascii=False)
        async with self._agent_send_lock:
            if settings.wire_encrypt:
                enc = self._encrypt_for_agent(text.encode("utf-8"))
                if enc is None:
                    logger.error("Refusing plaintext terminal control to agent (no terminal client key)")
                    return
                await agent.send_text(json.dumps({"enc": enc}, ensure_ascii=False))
            else:
                await agent.send_text(text)

    async def _agent_send_text(self, text: str) -> None:
        # kept for compatibility with older call sites
        try:
            await self._agent_send_control(json.loads(text) if text.startswith("{") else {"type": "text", "text": text})
        except json.JSONDecodeError:
            await self._agent_send_bytes(text.encode("utf-8"))


terminal_relay = TerminalRelay()
