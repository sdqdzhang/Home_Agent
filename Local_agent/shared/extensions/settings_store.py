"""扩展配置：包内默认 + 用户 data/<id>/settings.json。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from shared.extensions.contract import (
    SETTINGS_DEFAULTS_FILE,
    SETTINGS_USER_FILE,
    SettingFieldDecl,
)
from shared.extensions.manifest import ManifestError, load_manifest
from shared.extensions.state import load_installed_state, resolve_extension_path

logger = logging.getLogger(__name__)

_SECRET_MASK = "••••••••"


class SettingsError(ValueError):
    pass


def _base_dir() -> Path:
    from app.config import settings

    return settings.base_dir


def _data_dir(module_id: str, *, base_dir: Path | None = None) -> Path:
    root = base_dir or _base_dir()
    return root / "data" / module_id


def user_settings_path(module_id: str, *, base_dir: Path | None = None) -> Path:
    return _data_dir(module_id, base_dir=base_dir) / SETTINGS_USER_FILE


def package_defaults_path(root: Path) -> Path:
    return root / SETTINGS_DEFAULTS_FILE


def resolve_extension_root(module_id: str, *, base_dir: Path | None = None) -> Path:
    root = base_dir or _base_dir()
    state = load_installed_state(root)
    meta = state.extensions.get(module_id)
    if not meta or not meta.path:
        raise SettingsError(f"未安装: {module_id}")
    path = resolve_extension_path(root, meta.path)
    if not path.is_dir():
        raise SettingsError(f"扩展目录缺失: {path}")
    return path


def load_fields(module_id: str, *, base_dir: Path | None = None) -> tuple[SettingFieldDecl, ...]:
    from shared.extensions.registry import get_loaded

    loaded = get_loaded(module_id)
    if loaded:
        return loaded.manifest.settings
    try:
        manifest = load_manifest(resolve_extension_root(module_id, base_dir=base_dir))
    except ManifestError as exc:
        raise SettingsError(str(exc)) from exc
    return manifest.settings


def _read_yaml_or_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        data = yaml.safe_load(text) or {}
    else:
        data = json.loads(text or "{}")
    if not isinstance(data, dict):
        raise SettingsError(f"配置文件根必须是对象: {path}")
    return data


def load_package_defaults(root: Path, fields: tuple[SettingFieldDecl, ...]) -> dict[str, Any]:
    """schema.default ← settings.defaults.yaml（仅已知 key）。"""
    out: dict[str, Any] = {}
    for field in fields:
        if field.default is not None:
            out[field.key] = field.default
    pkg = package_defaults_path(root)
    if pkg.is_file():
        raw = _read_yaml_or_json(pkg)
        known = {f.key for f in fields}
        for key, val in raw.items():
            if key in known:
                out[str(key)] = val
    return out


def load_user_settings(module_id: str, *, base_dir: Path | None = None) -> dict[str, Any]:
    path = user_settings_path(module_id, base_dir=base_dir)
    if not path.is_file():
        return {}
    try:
        return _read_yaml_or_json(path)
    except Exception as exc:
        logger.warning("bad user settings for %s: %s", module_id, exc)
        return {}


def get_merged_values(module_id: str, *, base_dir: Path | None = None) -> dict[str, Any]:
    """生效配置：schema/包默认 ← 用户 settings.json。"""
    fields = load_fields(module_id, base_dir=base_dir)
    if not fields:
        return {}
    root = resolve_extension_root(module_id, base_dir=base_dir)
    merged = load_package_defaults(root, fields)
    user = load_user_settings(module_id, base_dir=base_dir)
    known = {f.key for f in fields}
    for key, val in user.items():
        if key in known:
            merged[str(key)] = val
    return merged


def get_value(module_id: str, key: str, default: Any = None, *, base_dir: Path | None = None) -> Any:
    values = get_merged_values(module_id, base_dir=base_dir)
    return values.get(key, default)


def _coerce_value(field: SettingFieldDecl, value: Any) -> Any:
    if value is None:
        if field.required:
            raise SettingsError(f"缺少必填项: {field.key}")
        return None
    t = field.type
    if t in ("string", "text", "secret", "select", "radio"):
        s = str(value)
        if field.required and not s.strip():
            raise SettingsError(f"缺少必填项: {field.key}")
        if t in ("select", "radio") and field.options:
            allowed = {o.value for o in field.options}
            if s not in allowed:
                raise SettingsError(f"{field.key} 取值无效: {s}")
        return s
    if t in ("number", "integer"):
        try:
            num = float(value)
        except (TypeError, ValueError) as exc:
            raise SettingsError(f"{field.key} 必须是数字") from exc
        if t == "integer":
            if abs(num - int(num)) > 1e-9:
                raise SettingsError(f"{field.key} 必须是整数")
            num = int(num)
        if field.min is not None and num < field.min:
            raise SettingsError(f"{field.key} 不能小于 {field.min}")
        if field.max is not None and num > field.max:
            raise SettingsError(f"{field.key} 不能大于 {field.max}")
        return num
    if t == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        s = str(value).strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
        raise SettingsError(f"{field.key} 必须是布尔值")
    if t in ("multiselect", "checkbox_group"):
        if isinstance(value, str):
            items = [value] if value else []
        elif isinstance(value, (list, tuple)):
            items = [str(x) for x in value]
        else:
            raise SettingsError(f"{field.key} 必须是数组")
        allowed = {o.value for o in field.options}
        bad = [x for x in items if x not in allowed]
        if bad:
            raise SettingsError(f"{field.key} 含无效选项: {bad}")
        if field.required and not items:
            raise SettingsError(f"缺少必填项: {field.key}")
        return items
    raise SettingsError(f"未知类型: {t}")


def validate_and_normalize(fields: tuple[SettingFieldDecl, ...], payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise SettingsError("配置必须是对象")
    known = {f.key: f for f in fields}
    out: dict[str, Any] = {}
    for key, field in known.items():
        if key not in payload:
            if field.required and field.default is None:
                raise SettingsError(f"缺少必填项: {key}")
            continue
        raw = payload[key]
        if field.type == "secret" and isinstance(raw, str) and raw == _SECRET_MASK:
            continue
        coerced = _coerce_value(field, raw)
        if coerced is not None:
            out[key] = coerced
        elif key in payload and payload[key] is None and not field.required:
            out[key] = None
    unknown = [k for k in payload if k not in known]
    if unknown:
        raise SettingsError(f"未知配置项: {unknown}")
    return out


def save_user_settings(
    module_id: str,
    payload: dict[str, Any],
    *,
    base_dir: Path | None = None,
) -> dict[str, Any]:
    fields = load_fields(module_id, base_dir=base_dir)
    if not fields:
        raise SettingsError("该扩展未声明 settings")
    existing = load_user_settings(module_id, base_dir=base_dir)
    normalized = validate_and_normalize(fields, payload)
    for field in fields:
        if field.type != "secret":
            continue
        if field.key not in normalized and field.key in existing:
            normalized[field.key] = existing[field.key]
        if field.key in payload and payload[field.key] == _SECRET_MASK and field.key in existing:
            normalized[field.key] = existing[field.key]
    merged_user = dict(existing)
    for key, val in normalized.items():
        if val is None:
            merged_user.pop(key, None)
        else:
            merged_user[key] = val
    known = {f.key for f in fields}
    merged_user = {k: v for k, v in merged_user.items() if k in known}

    path = user_settings_path(module_id, base_dir=base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged_user, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return get_merged_values(module_id, base_dir=base_dir)


def reset_user_settings(module_id: str, *, base_dir: Path | None = None) -> dict[str, Any]:
    path = user_settings_path(module_id, base_dir=base_dir)
    if path.is_file():
        path.unlink()
    return get_merged_values(module_id, base_dir=base_dir)


def _public_value(field: SettingFieldDecl, value: Any) -> Any:
    if field.type == "secret":
        if value is None or value == "":
            return ""
        return _SECRET_MASK
    return value


def field_to_public(field: SettingFieldDecl) -> dict[str, Any]:
    return {
        "key": field.key,
        "type": field.type,
        "label": field.label,
        "description": field.description,
        "default": field.default,
        "required": field.required,
        "placeholder": field.placeholder,
        "min": field.min,
        "max": field.max,
        "step": field.step,
        "group": field.group,
        "options": [{"value": o.value, "label": o.label or o.value} for o in field.options],
    }


def describe_settings(module_id: str, *, base_dir: Path | None = None) -> dict[str, Any]:
    fields = load_fields(module_id, base_dir=base_dir)
    merged = get_merged_values(module_id, base_dir=base_dir) if fields else {}
    user = load_user_settings(module_id, base_dir=base_dir)
    secrets_set = {
        f.key: bool(user.get(f.key) or merged.get(f.key))
        for f in fields
        if f.type == "secret"
    }
    return {
        "module_id": module_id,
        "fields": [field_to_public(f) for f in fields],
        "values": {f.key: _public_value(f, merged.get(f.key)) for f in fields},
        "secrets_set": secrets_set,
        "has_user_overrides": bool(user),
        "defaults_file": SETTINGS_DEFAULTS_FILE,
        "user_file": f"data/{module_id}/{SETTINGS_USER_FILE}",
    }


async def notify_settings_changed(module_id: str, values: dict[str, Any]) -> None:
    from shared.extensions.registry import get_loaded

    loaded = get_loaded(module_id)
    if not loaded:
        return
    hook = getattr(loaded.capability, "on_settings_changed", None)
    if not callable(hook):
        hook = getattr(loaded.service, "on_settings_changed", None)
    if not callable(hook):
        return
    try:
        maybe = hook(loaded.service, values)
        if hasattr(maybe, "__await__"):
            await maybe
    except Exception:
        logger.exception("on_settings_changed failed for %s", module_id)
