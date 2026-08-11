"""解析扩展 manifest.yaml。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from shared.extensions.contract import (
    CONTRACT_API_VERSION,
    ExtensionManifest,
    HttpDecl,
    LlmSlotDecl,
    ManifestEntry,
    PostInstallAction,
    ProvidesDecl,
    RequiresDecl,
    SettingFieldDecl,
    SettingOption,
    UiDecl,
    WsDecl,
    validate_manifest_id,
    validate_permissions,
    validate_post_install,
    validate_setting_field_types,
)


class ManifestError(ValueError):
    pass


def _as_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(x) for x in value)
    raise ManifestError(f"期望 list/str，收到 {type(value).__name__}")


def _parse_setting_options(raw: Any) -> tuple[SettingOption, ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ManifestError("settings.options 必须是列表")
    out: list[SettingOption] = []
    for item in raw:
        if isinstance(item, str):
            out.append(SettingOption(value=item, label=item))
            continue
        if not isinstance(item, dict):
            raise ManifestError("settings.options 项必须是字符串或对象")
        value = str(item.get("value") if "value" in item else item.get("id") or "").strip()
        if not value:
            raise ManifestError("settings.options.value 不能为空")
        out.append(SettingOption(value=value, label=str(item.get("label") or value)))
    return tuple(out)


def _parse_settings(raw: Any) -> tuple[SettingFieldDecl, ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ManifestError("settings 必须是列表")
    out: list[SettingFieldDecl] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict):
            raise ManifestError("settings 项必须是对象")
        key = str(item.get("key") or "").strip()
        if not key:
            raise ManifestError("settings.key 不能为空")
        if key in seen:
            raise ManifestError(f"settings.key 重复: {key}")
        seen.add(key)
        ftype = str(item.get("type") or "string").strip()
        options = _parse_setting_options(item.get("options"))
        if ftype in ("select", "radio", "multiselect", "checkbox_group") and not options:
            raise ManifestError(f"settings.{key} 类型 {ftype} 需要 options")
        min_v = item.get("min")
        max_v = item.get("max")
        step_v = item.get("step")
        out.append(
            SettingFieldDecl(
                key=key,
                type=ftype,  # type: ignore[arg-type]
                label=str(item.get("label") or key),
                description=str(item.get("description") or ""),
                default=item.get("default"),
                required=bool(item.get("required", False)),
                placeholder=str(item.get("placeholder") or ""),
                min=float(min_v) if min_v is not None and min_v != "" else None,
                max=float(max_v) if max_v is not None and max_v != "" else None,
                step=float(step_v) if step_v is not None and step_v != "" else None,
                options=options,
                group=str(item.get("group") or ""),
            )
        )
    bad = validate_setting_field_types(out)
    if bad:
        raise ManifestError(f"未知 settings.type: {bad}")
    return tuple(out)


def _parse_llm_slots(raw: Any) -> tuple[LlmSlotDecl, ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ManifestError("llm_slots 必须是列表")
    out: list[LlmSlotDecl] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ManifestError("llm_slots 项必须是对象")
        key = str(item.get("key") or "").strip()
        if not key:
            raise ManifestError("llm_slots.key 不能为空")
        cap = str(item.get("capability") or "chat").strip()
        if cap not in ("chat", "embed"):
            raise ManifestError(f"llm_slots.capability 无效: {cap}")
        out.append(
            LlmSlotDecl(
                key=key,
                capability=cap,  # type: ignore[arg-type]
                label=str(item.get("label") or key),
                description=str(item.get("description") or ""),
            )
        )
    return tuple(out)


def _parse_post_install(raw: Any) -> tuple[PostInstallAction, ...]:
    if not raw:
        return ()
    if not isinstance(raw, list):
        raise ManifestError("post_install 必须是列表")
    out: list[PostInstallAction] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ManifestError("post_install 项必须是对象")
        action = str(item.get("action") or "").strip()
        browsers = _as_tuple(item.get("browsers"))
        out.append(PostInstallAction(action=action, browsers=browsers))
    return tuple(out)


def parse_manifest_dict(data: dict[str, Any]) -> ExtensionManifest:
    if not isinstance(data, dict):
        raise ManifestError("manifest 根必须是对象")

    api_version = int(data.get("api_version") or 0)
    if api_version != CONTRACT_API_VERSION:
        raise ManifestError(f"不支持的 api_version={api_version}（需要 {CONTRACT_API_VERSION}）")

    module_id = str(data.get("id") or "").strip()
    if not validate_manifest_id(module_id):
        raise ManifestError(f"非法 id: {module_id!r}")

    tier = str(data.get("tier") or "extension").strip()
    if tier != "extension":
        raise ManifestError("tier 必须为 extension")

    name = str(data.get("name") or "").strip()
    if not name:
        raise ManifestError("name 不能为空")

    version = str(data.get("version") or "").strip()
    if not version:
        raise ManifestError("version 不能为空")

    entry_raw = data.get("entry") or {}
    if not isinstance(entry_raw, dict):
        raise ManifestError("entry 必须是对象")
    entry = ManifestEntry(capability=str(entry_raw.get("capability") or "capability"))

    provides_raw = data.get("provides") or {}
    if not isinstance(provides_raw, dict):
        raise ManifestError("provides 必须是对象")
    provides = ProvidesDecl(methods=_as_tuple(provides_raw.get("methods")))

    req_raw = data.get("requires") or {}
    if not isinstance(req_raw, dict):
        raise ManifestError("requires 必须是对象")
    requires = RequiresDecl(
        local_agent=str(req_raw.get("local_agent") or ""),
        python=str(req_raw.get("python") or ""),
        packages=_as_tuple(req_raw.get("packages")),
        modules=_as_tuple(req_raw.get("modules")),
    )

    ui_raw = data.get("ui") or {}
    if not isinstance(ui_raw, dict):
        raise ManifestError("ui 必须是对象")
    workspace = str(ui_raw.get("workspace") or "host")
    if workspace not in ("host", "none", "bundle"):
        raise ManifestError(f"ui.workspace 无效: {workspace}")
    ui = UiDecl(
        label=str(ui_raw.get("label") or name),
        icon=str(ui_raw.get("icon") or "◍"),
        default_msg_types=_as_tuple(ui_raw.get("default_msg_types")),
        workspace=workspace,  # type: ignore[arg-type]
    )

    http_raw = data.get("http") or {}
    if not isinstance(http_raw, dict):
        raise ManifestError("http 必须是对象")
    http = HttpDecl(router=str(http_raw.get("router") or ""))

    ws_raw = data.get("ws") or {}
    if not isinstance(ws_raw, dict):
        raise ManifestError("ws 必须是对象")
    channels_val = ws_raw.get("channels", "auto")
    if channels_val == "auto" or channels_val is None:
        channels: str | tuple[str, ...] = "auto"
    else:
        channels = _as_tuple(channels_val)
    ws = WsDecl(
        channels=channels,
        on_message=str(ws_raw.get("on_message") or "handle_incoming_message"),
        on_connect=str(ws_raw.get("on_connect") or ""),
    )

    permissions = _as_tuple(data.get("permissions"))
    bad_perm = validate_permissions(permissions)
    if bad_perm:
        raise ManifestError(f"未知 permissions: {bad_perm}")

    post_install = _parse_post_install(data.get("post_install"))
    bad_pi = validate_post_install(post_install)
    if bad_pi:
        raise ManifestError(f"未知 post_install.action: {bad_pi}")

    provides_tools = data.get("provides_tools", True)
    if not isinstance(provides_tools, bool):
        provides_tools = bool(provides_tools)

    return ExtensionManifest(
        api_version=api_version,
        id=module_id,
        name=name,
        version=version,
        tier="extension",
        description=str(data.get("description") or ""),
        aliases=_as_tuple(data.get("aliases")),
        entry=entry,
        provides=provides,
        provides_tools=provides_tools,
        llm_slots=_parse_llm_slots(data.get("llm_slots")),
        settings=_parse_settings(data.get("settings")),
        requires=requires,
        post_install=post_install,
        permissions=permissions,
        ui=ui,
        http=http,
        ws=ws,
        default_msg_type=str(data.get("default_msg_type") or "text"),
    )


def load_manifest(path: Path | str) -> ExtensionManifest:
    p = Path(path)
    if p.is_dir():
        p = p / "manifest.yaml"
    if not p.is_file():
        raise ManifestError(f"找不到 manifest: {p}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ManifestError(f"manifest 解析失败: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest 为空或格式错误")
    manifest = parse_manifest_dict(data)
    parent = p.parent
    if (parent / "capability.py").is_file() and parent.name != manifest.id:
        raise ManifestError(f"目录名 {parent.name!r} 与 manifest.id {manifest.id!r} 不一致")
    return manifest
