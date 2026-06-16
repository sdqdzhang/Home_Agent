import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import router
from app.config import settings
from app.crypto.rsa import ensure_server_keys
from app.models.db import clear_messages, init_db
from app.services.message_service import message_service
from app.services.ws_manager import ws_manager

logger = logging.getLogger(__name__)

server_private_key = None
server_public_key = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global server_private_key, server_public_key
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.keys_dir.mkdir(parents=True, exist_ok=True)
    server_private_key, server_public_key = ensure_server_keys(
        settings.keys_dir, settings.rsa_key_size
    )
    message_service.set_keys(server_private_key, server_public_key)
    init_db()
    deleted = clear_messages()
    if deleted:
        logger.info("Cleared %d message(s) from database on startup", deleted)
    yield


app = FastAPI(
    title="Server Center",
    description="HomeAgent message relay hub",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/{target}")
async def websocket_endpoint(websocket: WebSocket, target: str) -> None:
    await ws_manager.connect(target, websocket)
    try:
        await websocket.send_text(
            json.dumps({"event": "connected", "target": target}, ensure_ascii=False)
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(target, websocket)


static_dir = settings.static_dir
index_file = static_dir / "index.html"

if static_dir.exists() and index_file.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/")
    async def serve_index():
        return FileResponse(index_file)

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index_file)
else:

    @app.get("/")
    async def serve_index_fallback():
        return {
            "message": "Server Center API is running.",
            "docs": "/docs",
            "hint": "Run `cd frontend && npm install && npm run build` to enable Web UI.",
        }
