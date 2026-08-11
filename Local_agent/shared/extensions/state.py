"""installed.json 读写。"""

from __future__ import annotations

import json
from pathlib import Path

from shared.extensions.contract import (
    CONTRACT_API_VERSION,
    EXTENSIONS_DIR_NAME,
    INSTALLED_STATE_FILE,
    InstalledExtension,
    InstalledState,
)


def extensions_root(base_dir: Path) -> Path:
    return base_dir / EXTENSIONS_DIR_NAME


def installed_state_path(base_dir: Path) -> Path:
    return extensions_root(base_dir) / INSTALLED_STATE_FILE


def _ext_from_dict(data: dict) -> InstalledExtension:
    return InstalledExtension(
        version=str(data.get("version") or ""),
        enabled=bool(data.get("enabled", True)),
        installed_at=str(data.get("installed_at") or ""),
        path=str(data.get("path") or ""),
        status=data.get("status") or "ready",  # type: ignore[arg-type]
        error=str(data.get("error") or ""),
        pip_specs=tuple(data.get("pip_specs") or ()),
    )


def _ext_to_dict(ext: InstalledExtension, *, bundled: bool = False) -> dict:
    out = {
        "version": ext.version,
        "enabled": ext.enabled,
        "installed_at": ext.installed_at,
        "path": ext.path,
        "status": ext.status,
        "error": ext.error,
        "pip_specs": list(ext.pip_specs),
    }
    if bundled:
        out["bundled"] = True
    return out


def load_installed_state(base_dir: Path) -> InstalledState:
    path = installed_state_path(base_dir)
    if not path.is_file():
        return InstalledState()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return InstalledState()
    extensions: dict[str, InstalledExtension] = {}
    for key, val in (raw.get("extensions") or {}).items():
        if isinstance(val, dict):
            extensions[str(key)] = _ext_from_dict(val)
    return InstalledState(
        api_version=int(raw.get("api_version") or CONTRACT_API_VERSION),
        extensions=extensions,
    )


def save_installed_state(base_dir: Path, state: InstalledState, *, bundled_ids: set[str] | None = None) -> None:
    root = extensions_root(base_dir)
    root.mkdir(parents=True, exist_ok=True)
    bundled_ids = bundled_ids or set()
    # 保留已有 bundled 标记
    existing_bundled: set[str] = set()
    path = installed_state_path(base_dir)
    if path.is_file():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            for k, v in (prev.get("extensions") or {}).items():
                if isinstance(v, dict) and v.get("bundled"):
                    existing_bundled.add(str(k))
        except Exception:
            pass
    bundled_ids = bundled_ids | existing_bundled

    payload = {
        "api_version": state.api_version,
        "extensions": {
            mid: _ext_to_dict(ext, bundled=mid in bundled_ids)
            for mid, ext in sorted(state.extensions.items())
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_bundled(base_dir: Path, module_id: str) -> bool:
    path = installed_state_path(base_dir)
    if not path.is_file():
        return False
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        item = (raw.get("extensions") or {}).get(module_id) or {}
        return bool(item.get("bundled"))
    except Exception:
        return False


def resolve_extension_path(base_dir: Path, rel_or_abs: str) -> Path:
    p = Path(rel_or_abs)
    if p.is_absolute():
        return p
    return (base_dir / p).resolve()
