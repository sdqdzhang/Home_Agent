from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from shared.server_center import ServerCenterClient, WebSocketListener, ensure_client_keys
from modules.crawler import MODULE_ID as CRAWLER_ID
from modules.crawler.router import router as crawler_router
from modules.crawler.service import CrawlerService
from modules.env import MODULE_ID as ENV_ID
from modules.env.router import router as env_router
from modules.env.service import EnvService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

crawler_service: CrawlerService | None = None
env_service: EnvService | None = None
_ws_listeners: list[WebSocketListener] = []


async def _register_module_client(module_name: str, id_prefix: str) -> ServerCenterClient:
    private_key, public_key = ensure_client_keys(settings.keys_dir, settings.rsa_key_size)
    client = ServerCenterClient(
        settings.server_center_url,
        module_name,
        private_key,
        public_key,
        id_prefix=id_prefix,
    )
    try:
        await client.ensure_registered()
        logger.info("Registered %s with Server Center at %s", module_name, settings.server_center_url)
    except Exception:
        logger.warning("Could not register %s with Server Center (is it running?)", module_name)
    return client


async def _start_ws_listeners(channels: tuple[str, ...], handler) -> None:
    for channel in channels:
        listener = WebSocketListener(settings.server_center_url, channel)
        listener.on_message(handler)
        await listener.start()
        _ws_listeners.append(listener)
        logger.info("WebSocket listener started on channel: %s", channel)


def _dedupe_ws_handler(handler, *, ttl_seconds: float = 120):
    """同一消息 id 只处理一次（避免多频道重复广播）。"""
    seen: dict[str, float] = {}

    async def wrapped(data: dict) -> None:
        import time

        msg_id = data.get("id")
        if msg_id:
            now = time.monotonic()
            expired = [k for k, t in seen.items() if now - t > ttl_seconds]
            for k in expired:
                del seen[k]
            if msg_id in seen:
                return
            seen[msg_id] = now
        await handler(data)

    return wrapped


@asynccontextmanager
async def lifespan(_: FastAPI):
    global crawler_service, env_service, _ws_listeners

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.keys_dir.mkdir(parents=True, exist_ok=True)

    crawler_client = await _register_module_client("网页爬取模块", "crawler")
    env_client = await _register_module_client("环境感知模块", "env")

    crawler_service = CrawlerService(server_client=crawler_client)
    env_service = EnvService(server_client=env_client)
    await env_service.start(use_model=True)

    await _start_ws_listeners((CRAWLER_ID,), _dedupe_ws_handler(crawler_service.handle_incoming_message))
    await _start_ws_listeners((ENV_ID,), _dedupe_ws_handler(env_service.handle_incoming_message))

    yield

    await env_service.stop()
    for listener in _ws_listeners:
        await listener.stop()
    _ws_listeners.clear()


app = FastAPI(
    title="HomeAgent Local Agent",
    description="本地智能体服务 — 含网页爬取、环境感知等模块",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(crawler_router)
app.include_router(env_router)


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "modules": {
            "crawler": crawler_service is not None,
            "env": env_service is not None,
        },
    }
