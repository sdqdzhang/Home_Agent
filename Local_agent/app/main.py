from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from app.config import settings
from shared.server_center import ServerCenterClient, WebSocketListener, ensure_client_keys
from shared.llm import LlmConfigService, MODULE_ID as LLM_ID, get_model_registry
from modules.env import MODULE_ID as ENV_ID
from modules.env.router import router as env_router
from modules.env.service import EnvService
from modules.rag import MODULE_ID as RAG_ID
from modules.rag.router import router as rag_router
from modules.rag.service import RagService
from modules.security import MODULE_ID as SECURITY_ID, MODULE_NAME as SECURITY_NAME
from modules.security.router import router as security_router
from modules.security.service import SecurityService
from modules.memory import MODULE_ID as MEMORY_ID
from modules.memory.router import router as memory_router
from modules.memory.service import MemoryService
from modules.executor import MODULE_ID as EXECUTOR_ID
from modules.executor.router import router as executor_router
from modules.executor.service import ExecutorService
from modules.processor import MODULE_ID as PROCESSOR_ID
from modules.processor.router import router as processor_router
from modules.processor.service import ProcessorService
from modules.planning import MODULE_ID as PLANNING_ID
from modules.planning.service import PlanningService
from modules.main import MODULE_ID as MAIN_ID
from modules.main.service import MainService
from modules.conversation_manager import MODULE_ID as CM_ID
from modules.conversation_manager.service import ConversationManagerService
from modules.emotion import MODULE_ID as EMOTION_ID
from modules.emotion.service import EmotionService
from modules.terminal.bridge import TerminalBridge
from modules.crawler.router import router as crawler_router
from shared.extensions.installer import ensure_default_bundled
from shared.extensions.loader import LoaderHost, load_all_enabled, set_host
from shared.extensions.registry import list_loaded_ids
from shared.extensions.router import router as extensions_router
from shared.local_bus import list_registered_module_ids

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)

crawler_service: Any | None = None
env_service: EnvService | None = None
rag_service: RagService | None = None
security_service: SecurityService | None = None
memory_service: MemoryService | None = None
executor_service: ExecutorService | None = None
processor_service: ProcessorService | None = None
planning_service: PlanningService | None = None
main_service: MainService | None = None
conversation_manager_service: ConversationManagerService | None = None
emotion_service: EmotionService | None = None
llm_config_service: LlmConfigService | None = None
terminal_bridge: TerminalBridge | None = None
_ws_listeners: list[WebSocketListener] = []


async def _register_module_client(
    module_name: str,
    id_prefix: str,
    *extra_client_ids: str,
) -> ServerCenterClient:
    private_key, public_key = ensure_client_keys(settings.keys_dir, settings.rsa_key_size)
    client = ServerCenterClient(
        settings.server_center_url,
        module_name,
        private_key,
        public_key,
        id_prefix=id_prefix,
        wire_encrypt=settings.wire_encrypt,
    )
    try:
        await client.ensure_registered(*extra_client_ids)
        logger.info("Registered %s with Server Center at %s", module_name, settings.server_center_url)
    except Exception:
        logger.warning("Could not register %s with Server Center (is it running?)", module_name)
    return client


async def _start_ws_listeners(
    channels: tuple[str, ...],
    handler,
    *,
    on_connect=None,
) -> list[WebSocketListener]:
    private_key, _ = ensure_client_keys(settings.keys_dir, settings.rsa_key_size)
    created: list[WebSocketListener] = []
    for channel in channels:
        listener = WebSocketListener(
            settings.server_center_url,
            channel,
            private_key=private_key,
            wire_encrypt=settings.wire_encrypt,
        )
        listener.on_message(handler)
        if on_connect is not None:
            listener.on_connect(on_connect)
        await listener.start()
        _ws_listeners.append(listener)
        created.append(listener)
        logger.info("WebSocket listener started on channel: %s", channel)
    return created


def _dedupe_ws_handler(handler, *, ttl_seconds: float = 120):
    """同一消息 id 只处理一次（避免多频道重复广播）。"""
    seen: dict[str, float] = {}

    async def wrapped(data: dict) -> None:
        import time

        status = data.get("status")
        # 审批/质询结果必须与 pending 的 new_message 分开处理，否则会吞掉放行信号
        if status in ("approved", "rejected", "answered", "handled"):
            await handler(data)
            return

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
    global crawler_service, env_service, rag_service, security_service, memory_service, executor_service, processor_service, planning_service, main_service, conversation_manager_service, emotion_service, llm_config_service, terminal_bridge, _ws_listeners

    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.keys_dir.mkdir(parents=True, exist_ok=True)

    registry = get_model_registry()
    if registry.ensure_seeded():
        logger.info("LLM config DB seeded from .env defaults")

    ensure_default_bundled(settings.base_dir)
    set_host(
        LoaderHost(
            base_dir=settings.base_dir,
            register_client=_register_module_client,
            start_ws=_start_ws_listeners,
            dedupe_handler=_dedupe_ws_handler,
            ws_by_module={},
        )
    )

    env_client = await _register_module_client("环境感知模块", "env", ENV_ID)
    rag_client = await _register_module_client("RAG模块", "rag", RAG_ID)
    security_client = await _register_module_client("安全检查模块", "security", SECURITY_ID, SECURITY_NAME)
    memory_client = await _register_module_client("记忆模块", "memory", MEMORY_ID)
    executor_client = await _register_module_client("执行模块", "executor", EXECUTOR_ID)
    processor_client = await _register_module_client("处理", "processor", PROCESSOR_ID)
    planning_client = await _register_module_client("规划模块", "planning", PLANNING_ID)
    main_client = await _register_module_client("主对话", "main", MAIN_ID)
    cm_client = await _register_module_client("会话管理", "cm", CM_ID)
    emotion_client = await _register_module_client("情感与性格状态模块", "emotion", EMOTION_ID)
    llm_client = await _register_module_client("本地Agent", "llm", LLM_ID)
    await _register_module_client("terminal", "terminal")

    env_service = EnvService(server_client=env_client)
    rag_service = RagService(server_client=rag_client)
    security_service = SecurityService(server_client=security_client)
    memory_service = MemoryService(server_client=memory_client)
    executor_service = ExecutorService(server_client=executor_client)
    processor_service = ProcessorService(server_client=processor_client)
    planning_service = PlanningService(server_client=planning_client)
    main_service = MainService(server_client=main_client)
    conversation_manager_service = ConversationManagerService(server_client=cm_client)
    emotion_service = EmotionService(server_client=emotion_client)
    llm_config_service = LlmConfigService(server_client=llm_client)
    await env_service.start(use_model=True)

    await _start_ws_listeners((ENV_ID,), _dedupe_ws_handler(env_service.handle_incoming_message))
    await _start_ws_listeners((RAG_ID,), _dedupe_ws_handler(rag_service.handle_incoming_message))
    await _start_ws_listeners(
        (SECURITY_ID, SECURITY_NAME),
        _dedupe_ws_handler(security_service.handle_ws_event),
    )
    await _start_ws_listeners((MEMORY_ID,), _dedupe_ws_handler(memory_service.handle_incoming_message))
    await _start_ws_listeners((EXECUTOR_ID,), _dedupe_ws_handler(executor_service.handle_incoming_message))
    await _start_ws_listeners((PROCESSOR_ID,), _dedupe_ws_handler(processor_service.handle_incoming_message))
    await _start_ws_listeners((PLANNING_ID,), _dedupe_ws_handler(planning_service.handle_incoming_message))
    await _start_ws_listeners((MAIN_ID,), _dedupe_ws_handler(main_service.handle_incoming_message))
    await _start_ws_listeners((CM_ID,), _dedupe_ws_handler(conversation_manager_service.handle_incoming_message))
    await _start_ws_listeners((EMOTION_ID,), _dedupe_ws_handler(emotion_service.handle_incoming_message))
    await _start_ws_listeners((LLM_ID,), _dedupe_ws_handler(llm_config_service.handle_incoming_message))

    try:
        loaded = await load_all_enabled()
        logger.info("extensions loaded: %s", [e.manifest.id for e in loaded])
    except Exception:
        logger.exception("failed to load extensions")

    terminal_bridge = TerminalBridge()
    await terminal_bridge.start()

    yield

    await env_service.stop()
    if terminal_bridge:
        await terminal_bridge.stop()
    for listener in _ws_listeners:
        await listener.stop()
    _ws_listeners.clear()


app = FastAPI(
    title="HomeAgent Local Agent",
    description="本地智能体服务 — 含网页爬取、环境感知、RAG 等模块",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(crawler_router)
app.include_router(env_router)
app.include_router(rag_router)
app.include_router(security_router)
app.include_router(memory_router)
app.include_router(executor_router)
app.include_router(processor_router)
app.include_router(extensions_router)


@app.get("/health")
def health() -> dict[str, object]:
    modules = {
        "env": env_service is not None,
        "rag": rag_service is not None,
        "security": security_service is not None,
        "memory": memory_service is not None,
        "executor": executor_service is not None,
        "processor": processor_service is not None,
        "planning": planning_service is not None,
        "main": main_service is not None,
        "conversation_manager": conversation_manager_service is not None,
        "emotion": emotion_service is not None,
        "llm_config": llm_config_service is not None,
        "terminal": terminal_bridge is not None and terminal_bridge.running,
    }
    for mid in list_loaded_ids():
        modules[mid] = True
    # crawler 可能未加载
    if "crawler" not in modules:
        modules["crawler"] = crawler_service is not None
    return {
        "status": "ok",
        "modules": modules,
        "extensions": sorted(list_loaded_ids()),
        "registered": sorted(list_registered_module_ids()),
    }
