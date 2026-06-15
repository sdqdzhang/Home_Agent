import json
from collections import defaultdict

from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, target: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[target].add(websocket)

    def disconnect(self, target: str, websocket: WebSocket) -> None:
        self._connections[target].discard(websocket)
        if not self._connections[target]:
            del self._connections[target]

    async def broadcast(self, target: str, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections.get(target, set()):
            try:
                await ws.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(target, ws)


ws_manager = WebSocketManager()
