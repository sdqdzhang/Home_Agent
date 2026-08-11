"""运行时已加载扩展注册表。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from shared.extensions.contract import ExtensionManifest, ToolSpec


@dataclass
class LoadedExtension:
    manifest: ExtensionManifest
    root: Path
    service: Any
    capability: Any
    tools: list[ToolSpec] = field(default_factory=list)
    bundled: bool = False


_LOADED: dict[str, LoadedExtension] = {}


def get_loaded(module_id: str) -> LoadedExtension | None:
    return _LOADED.get(module_id)


def list_loaded() -> list[LoadedExtension]:
    return list(_LOADED.values())


def list_loaded_ids() -> set[str]:
    return set(_LOADED)


def put_loaded(ext: LoadedExtension) -> None:
    _LOADED[ext.manifest.id] = ext


def pop_loaded(module_id: str) -> LoadedExtension | None:
    return _LOADED.pop(module_id, None)


def clear_loaded() -> None:
    _LOADED.clear()


def extension_tool_specs() -> list[ToolSpec]:
    out: list[ToolSpec] = []
    for ext in _LOADED.values():
        out.extend(ext.tools)
    return out


def find_tool_spec(name: str) -> ToolSpec | None:
    for spec in extension_tool_specs():
        if spec.name == name:
            return spec
    return None
