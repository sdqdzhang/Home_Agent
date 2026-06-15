from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.server_client.crypto import ensure_client_keys
from app.server_client.message_client import ServerCenterClient
from app.server_client.ws_listener import WebSocketListener
from modules.crawler.router import router as crawler_router
from modules.crawler.service import CrawlerService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

crawler_service: CrawlerService | None = None
_ws_listeners: list[WebSocketListener] = []


@asynccontextmanager
async def lifespan(_: FastAPI):
    global crawler_service, _ws_listeners

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.keys_dir.mkdir(parents=True, exist_ok=True)

    private_key, public_key = ensure_client_keys(settings.keys_dir, settings.rsa_key_size)
    server_client = ServerCenterClient(
        settings.server_center_url,
        settings.module_name,
        private_key,
        public_key,
    )

    try:
        await server_client.ensure_registered()
        logger.info("Registered with Server Center at %s", settings.server_center_url)
    except Exception:
        logger.warning("Could not register with Server Center (is it running?)")

    crawler_service = CrawlerService(server_client=server_client)

    for channel in ("网页爬取模块", "crawler"):
        listener = WebSocketListener(settings.server_center_url, channel)
        listener.on_message(crawler_service.handle_incoming_message)
        await listener.start()
        _ws_listeners.append(listener)
        logger.info("WebSocket listener started on channel: %s", channel)

    yield

    for listener in _ws_listeners:
        await listener.stop()
    _ws_listeners.clear()


app = FastAPI(
    title="HomeAgent Local Agent",
    description="本地智能体服务 — 含网页爬取等模块",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(crawler_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "module": "crawler"}
