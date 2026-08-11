"""扩展模块契约类型（v1）。

权威说明见 docs/extension-contract.md。
本模块只定义数据结构与常量；不含 loader / 安装器。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CONTRACT_API_VERSION = 1

PACKAGE_SUFFIX = ".hamod"

EXTENSIONS_DIR_NAME = "extensions"
INSTALLED_STATE_FILE = "installed.json"

# Local HTTP 路径约定（实现时挂到 Local Agent app）
HTTP_PREFIX = "/extensions"
HTTP_INSTALL = "/extensions/install"
HTTP_LIST = "/extensions"
HTTP_ITEM = "/extensions/{id}"

Tier = Literal["extension"]

Permission = Literal[
    "network",
    "fs_data",
    "fs_workspace",
    "subprocess",
    "call_modules",
]

KNOWN_PERMISSIONS: frozenset[str] = frozenset(
    {"network", "fs_data", "fs_workspace", "subprocess", "call_modules"}
)

# post_install.action 白名单
POST_INSTALL_ACTIONS: frozenset[str] = frozenset({"playwright_install"})

ExtensionStatus = Literal["ready", "unavailable", "error"]

WorkspaceMode = Literal["host", "none", "bundle"]

# 与 shared.llm.schemas.Capability 对齐
LlmSlotCapability = Literal["chat", "embed"]

ApplyMode = Literal["reloaded", "restart_required"]

# 扩展配置表单控件类型（通用 UI）
SettingFieldType = Literal[
    "string",
    "text",
    "number",
    "integer",
    "boolean",
    "secret",
    "select",
    "radio",
    "multiselect",
    "checkbox_group",
]

KNOWN_SETTING_FIELD_TYPES: frozenset[str] = frozenset(
    {
        "string",
        "text",
        "number",
        "integer",
        "boolean",
        "secret",
        "select",
        "radio",
        "multiselect",
        "checkbox_group",
    }
)

SETTINGS_DEFAULTS_FILE = "settings.defaults.yaml"
SETTINGS_USER_FILE = "settings.json"


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestEntry:
    capability: str = "capability"


@dataclass(frozen=True)
class SettingOption:
    value: str
    label: str = ""


@dataclass(frozen=True)
class SettingFieldDecl:
    """扩展可配置项；前端按 type 渲染通用表单。"""

    key: str
    type: SettingFieldType = "string"
    label: str = ""
    description: str = ""
    default: Any = None
    required: bool = False
    placeholder: str = ""
    min: float | None = None
    max: float | None = None
    step: float | None = None
    options: tuple[SettingOption, ...] = ()
    # 分组标题（同 group 的字段排在一起）
    group: str = ""


@dataclass(frozen=True)
class LlmSlotDecl:
    key: str
    capability: LlmSlotCapability = "chat"
    label: str = ""
    description: str = ""


@dataclass(frozen=True)
class RequiresDecl:
    local_agent: str = ""
    python: str = ""
    packages: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()


@dataclass(frozen=True)
class PostInstallAction:
    """白名单动作；未知 action 安装失败。"""

    action: str
    browsers: tuple[str, ...] = ()  # playwright_install


@dataclass(frozen=True)
class UiDecl:
    label: str = ""
    icon: str = "◍"
    default_msg_types: tuple[str, ...] = ()
    workspace: WorkspaceMode = "host"


@dataclass(frozen=True)
class HttpDecl:
    router: str = ""


@dataclass(frozen=True)
class WsDecl:
    channels: str | tuple[str, ...] = "auto"
    on_message: str = "handle_incoming_message"
    on_connect: str = ""


@dataclass(frozen=True)
class ProvidesDecl:
    methods: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtensionManifest:
    api_version: int
    id: str
    name: str
    version: str
    tier: Tier = "extension"
    description: str = ""
    aliases: tuple[str, ...] = ()
    entry: ManifestEntry = field(default_factory=ManifestEntry)
    provides: ProvidesDecl = field(default_factory=ProvidesDecl)
    provides_tools: bool = True
    llm_slots: tuple[LlmSlotDecl, ...] = ()
    settings: tuple[SettingFieldDecl, ...] = ()
    requires: RequiresDecl = field(default_factory=RequiresDecl)
    post_install: tuple[PostInstallAction, ...] = ()
    permissions: tuple[str, ...] = ()
    ui: UiDecl = field(default_factory=UiDecl)
    http: HttpDecl = field(default_factory=HttpDecl)
    ws: WsDecl = field(default_factory=WsDecl)
    default_msg_type: str = "text"

    def channel_names(self) -> tuple[str, ...]:
        if self.ws.channels == "auto":
            names = [self.id, self.name, *self.aliases]
            seen: set[str] = set()
            out: list[str] = []
            for n in names:
                if n and n not in seen:
                    seen.add(n)
                    out.append(n)
            return tuple(out)
        return tuple(self.ws.channels)


# ---------------------------------------------------------------------------
# 安装态 / 安装结果
# ---------------------------------------------------------------------------


@dataclass
class InstalledExtension:
    version: str
    enabled: bool = True
    installed_at: str = ""
    path: str = ""
    status: ExtensionStatus = "ready"
    error: str = ""
    pip_specs: tuple[str, ...] = ()


@dataclass
class InstalledState:
    api_version: int = CONTRACT_API_VERSION
    extensions: dict[str, InstalledExtension] = field(default_factory=dict)


@dataclass(frozen=True)
class InstallResult:
    module_id: str
    version: str
    apply: ApplyMode
    message: str = ""


@dataclass(frozen=True)
class UninstallResult:
    module_id: str
    apply: ApplyMode
    message: str = ""


# ---------------------------------------------------------------------------
# ToolSpec
# ---------------------------------------------------------------------------

ToolTier = Literal["core", "extension"]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    module_id: str
    method: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    tier: ToolTier = "extension"
    when: str = ""


# ---------------------------------------------------------------------------
# Protocols
# ---------------------------------------------------------------------------


@runtime_checkable
class ExtensionCapability(Protocol):
    TOOLS: list[ToolSpec]

    def create_service(self, *, server_client: Any, manifest: ExtensionManifest) -> Any: ...


@runtime_checkable
class ExtensionService(Protocol):
    server: Any

    async def handle_incoming_message(self, data: dict[str, Any]) -> None: ...


def validate_manifest_id(module_id: str) -> bool:
    if not module_id or not module_id[0].isalpha() or not module_id[0].islower():
        return False
    return all(c.islower() or c.isdigit() or c == "_" for c in module_id)


def validate_setting_field_types(fields: tuple[SettingFieldDecl, ...] | list[SettingFieldDecl]) -> list[str]:
    return [f.type for f in fields if f.type not in KNOWN_SETTING_FIELD_TYPES]


def validate_permissions(permissions: tuple[str, ...] | list[str]) -> list[str]:
    return [p for p in permissions if p not in KNOWN_PERMISSIONS]


def validate_post_install(actions: tuple[PostInstallAction, ...] | list[PostInstallAction]) -> list[str]:
    """返回未知 action 名；空表示全部合法。"""
    return [a.action for a in actions if a.action not in POST_INSTALL_ACTIONS]
