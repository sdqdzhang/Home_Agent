"""扩展加载 / 卸载（同进程 apply）。"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.extensions.contract import ExtensionManifest, ToolSpec
from shared.extensions.manifest import ManifestError, load_manifest
from shared.extensions.registry import LoadedExtension, clear_loaded, get_loaded, list_loaded, pop_loaded, put_loaded
from shared.extensions.slots_dyn import register_extension_llm_slots, unregister_extension_llm_slots
from shared.extensions.state import (
    is_bundled,
    load_installed_state,
    resolve_extension_path,
    save_installed_state,
)
from shared.local_bus import register_service, unregister_service

logger = logging.getLogger(__name__)

RegisterClientFn = Callable[..., Awaitable[Any]]
StartWsFn = Callable[..., Awaitable[None]]
DedupeFn = Callable[[Any], Any]


@dataclass
class LoaderHost:
    """宿主回调：由 app.main 注入。"""

    base_dir: Path
    register_client: RegisterClientFn
    start_ws: StartWsFn
    dedupe_handler: DedupeFn
    # module_id → 已启动的 WS listener 列表，便于卸载时 stop
    ws_by_module: dict[str, list[Any]]


_host: LoaderHost | None = None


def set_host(host: LoaderHost) -> None:
    global _host
    _host = host


def get_host() -> LoaderHost:
    if _host is None:
        raise RuntimeError("extension loader host 未初始化")
    return _host


def _import_capability(root: Path, manifest: ExtensionManifest) -> Any:
    cap_name = manifest.entry.capability or "capability"
    base = get_host().base_dir.resolve()
    try:
        rel = root.resolve().relative_to(base)
        parts = list(rel.parts)
        if parts:
            mod_path = ".".join([*parts, cap_name])
            try:
                if mod_path in sys.modules:
                    return importlib.reload(sys.modules[mod_path])
                return importlib.import_module(mod_path)
            except ImportError:
                logger.debug("package import failed for %s, fallback to file", mod_path)
    except (ValueError, RuntimeError):
        pass

    # 外置 extensions/<id>/capability.py
    file_path = root / f"{cap_name}.py"
    if not file_path.is_file():
        raise ManifestError(f"找不到 capability: {file_path}")
    mod_name = f"homeagent_ext_{manifest.id}_{cap_name}"
    spec = importlib.util.spec_from_file_location(mod_name, file_path)
    if spec is None or spec.loader is None:
        raise ManifestError(f"无法加载 capability: {file_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    root_str = str(root.resolve())
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    spec.loader.exec_module(module)
    return module


def _collect_tools(capability: Any, manifest: ExtensionManifest) -> list[ToolSpec]:
    if not manifest.provides_tools:
        return []
    raw = getattr(capability, "TOOLS", None) or []
    out: list[ToolSpec] = []
    for item in raw:
        if isinstance(item, ToolSpec):
            spec = item
        elif hasattr(item, "name") and hasattr(item, "module_id") and hasattr(item, "method"):
            spec = ToolSpec(
                name=str(item.name),
                module_id=str(item.module_id),
                method=str(item.method),
                description=str(getattr(item, "description", "") or ""),
                parameters=dict(getattr(item, "parameters", {}) or {}),
                tier=getattr(item, "tier", "extension"),  # type: ignore[arg-type]
                when=str(getattr(item, "when", "") or ""),
            )
        else:
            raise ManifestError(f"无效 ToolSpec: {item!r}")
        if spec.module_id != manifest.id:
            raise ManifestError(f"工具 {spec.name} module_id={spec.module_id} 与扩展 id={manifest.id} 不一致")
        if spec.tier != "extension":
            raise ManifestError(f"工具 {spec.name} tier 必须为 extension")
        out.append(spec)
    return out


async def load_one(module_id: str, *, root: Path, bundled: bool = False) -> LoadedExtension:
    host = get_host()
    if get_loaded(module_id):
        await unload_one(module_id)

    manifest = load_manifest(root)
    if manifest.id != module_id:
        raise ManifestError(f"path 中 id={manifest.id} 与请求 {module_id} 不一致")

    capability = _import_capability(root, manifest)
    create_service = getattr(capability, "create_service", None)
    if not callable(create_service):
        raise ManifestError("capability.create_service 缺失")

    tools = _collect_tools(capability, manifest)

    client = await host.register_client(manifest.name, manifest.id, *manifest.channel_names())
    service = create_service(server_client=client, manifest=manifest)
    register_service(manifest.id, service)

    register_extension_llm_slots(manifest.id, manifest.llm_slots)
    try:
        from shared.llm import get_model_registry
        from shared.llm.seed import ensure_bindings_for_slots

        ensure_bindings_for_slots(
            get_model_registry()._store,  # noqa: SLF001
            [s.key for s in manifest.llm_slots],
        )
    except Exception:
        logger.exception("failed to seed bindings for %s slots", manifest.id)

    on_message_name = manifest.ws.on_message or "handle_incoming_message"
    handler = getattr(service, on_message_name, None)
    on_connect = None
    if manifest.ws.on_connect:
        on_connect = getattr(service, manifest.ws.on_connect, None)

    listeners: list[Any] = []
    if callable(handler):
        listeners = await host.start_ws(
            tuple(manifest.channel_names()),
            host.dedupe_handler(handler),
            on_connect=on_connect if callable(on_connect) else None,
        )
        host.ws_by_module[manifest.id] = list(listeners or [])

    on_loaded = getattr(capability, "on_loaded", None)
    if callable(on_loaded):
        maybe = on_loaded(service, ctx={"root": root, "manifest": manifest})
        if hasattr(maybe, "__await__"):
            await maybe

    loaded = LoadedExtension(
        manifest=manifest,
        root=root,
        service=service,
        capability=capability,
        tools=tools,
        bundled=bundled,
    )
    put_loaded(loaded)

    # 同步 app.main.crawler_service 等兼容别名
    try:
        from app import main as app_main

        attr = f"{manifest.id}_service"
        if hasattr(app_main, attr) or manifest.id == "crawler":
            setattr(app_main, "crawler_service" if manifest.id == "crawler" else attr, service)
    except Exception:
        logger.debug("skip main alias for %s", manifest.id, exc_info=True)

    logger.info("extension loaded: %s v%s (%s)", manifest.id, manifest.version, root)
    return loaded


async def unload_one(module_id: str, *, purge_slots: bool = True) -> None:
    host = get_host()
    loaded = pop_loaded(module_id)
    if not loaded:
        unregister_service(module_id)
        if purge_slots:
            unregister_extension_llm_slots(module_id)
        return

    on_unload = getattr(loaded.capability, "on_unload", None)
    if callable(on_unload):
        try:
            maybe = on_unload(loaded.service, ctx={"root": loaded.root, "manifest": loaded.manifest})
            if hasattr(maybe, "__await__"):
                await maybe
        except Exception:
            logger.exception("on_unload failed for %s", module_id)

    for listener in host.ws_by_module.pop(module_id, []):
        try:
            await listener.stop()
        except Exception:
            logger.exception("stop ws failed for %s", module_id)
        try:
            from app import main as app_main

            if listener in app_main._ws_listeners:
                app_main._ws_listeners.remove(listener)
        except Exception:
            pass

    unregister_service(module_id)
    if purge_slots:
        unregister_extension_llm_slots(module_id)

    try:
        from app import main as app_main

        if module_id == "crawler":
            app_main.crawler_service = None
    except Exception:
        pass

    logger.info("extension unloaded: %s", module_id)


async def load_all_enabled() -> list[LoadedExtension]:
    host = get_host()
    state = load_installed_state(host.base_dir)
    loaded: list[LoadedExtension] = []
    for module_id, meta in state.extensions.items():
        if not meta.enabled:
            continue
        root = resolve_extension_path(host.base_dir, meta.path)
        if not root.is_dir():
            logger.error("extension path missing: %s -> %s", module_id, root)
            meta.status = "error"
            meta.error = f"path missing: {root}"
            continue
        try:
            ext = await load_one(module_id, root=root, bundled=is_bundled(host.base_dir, module_id))
            meta.status = "ready"
            meta.error = ""
            loaded.append(ext)
        except Exception as exc:
            logger.exception("failed to load extension %s", module_id)
            meta.status = "error"
            meta.error = str(exc)
    save_installed_state(host.base_dir, state)
    return loaded


async def apply_reload() -> str:
    """卸载全部已加载扩展后按 installed.json 重载。返回 ApplyMode。"""
    for mid in list(list_loaded_ids_safe()):
        await unload_one(mid)
    clear_loaded()
    await load_all_enabled()
    return "reloaded"


def list_loaded_ids_safe() -> set[str]:
    return {e.manifest.id for e in list_loaded()}
