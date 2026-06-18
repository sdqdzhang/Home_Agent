from dataclasses import dataclass


@dataclass(frozen=True)
class ModuleDef:
    id: str
    label: str
    names: tuple[str, ...]
    description: str
    default_msg_types: tuple[str, ...] = ()
    icon: str = "🤖"


MODULES: tuple[ModuleDef, ...] = (
    ModuleDef(
        id="jarvis",
        label="主对话",
        names=("jarvis", "Jarvis", "主对话"),
        description="与 Jarvis 主智能体的日常对话入口",
        default_msg_types=("text",),
        icon="💬",
    ),
    ModuleDef(
        id="emotion",
        label="情感与性格状态模块",
        names=("情感与性格状态模块", "emotion", "persona"),
        description="情感、性格与情绪状态的感知与表达",
        default_msg_types=("persona_state", "text"),
        icon="💭",
    ),
    ModuleDef(
        id="security",
        label="安全检查模块",
        names=("安全检查模块", "security"),
        description="危险操作审批与安全策略校验",
        default_msg_types=("approval_request", "security_yellow_log", "text"),
        icon="🛡️",
    ),
    ModuleDef(
        id="env",
        label="环境感知模块",
        names=("环境感知模块", "env_sense", "env"),
        description="系统与环境状态静默上报",
        default_msg_types=("system_status", "desktop_screenshot", "camera_capture"),
        icon="📡",
    ),
    ModuleDef(
        id="memory",
        label="记忆模块",
        names=("记忆模块", "memory"),
        description="记忆的写入、检索、压缩与反思",
        default_msg_types=("memory_record", "text"),
        icon="🧠",
    ),
    ModuleDef(
        id="crawler",
        label="网页爬取模块",
        names=("网页爬取模块", "crawler"),
        description="网页抓取任务与结果日志",
        default_msg_types=("execution_log",),
        icon="🕷️",
    ),
    ModuleDef(
        id="rag",
        label="RAG 模块",
        names=("RAG模块", "RAG 模块", "rag"),
        description="检索增强生成：查询、召回与回答",
        default_msg_types=("rag_result", "text"),
        icon="📚",
    ),
    ModuleDef(
        id="executor",
        label="执行模块",
        names=("执行模块", "executor", "execution"),
        description="命令与任务执行过程日志",
        default_msg_types=("execution_log",),
        icon="⚡",
    ),
    ModuleDef(
        id="reflection",
        label="自省与纠错模块",
        names=("自省与纠错模块", "reflection", "introspection"),
        description="自我反思、错误分析与纠正建议",
        default_msg_types=("reflection_note", "text"),
        icon="🔍",
    ),
    ModuleDef(
        id="llm",
        label="模型配置",
        names=("本地Agent", "local_agent", "llm"),
        description="Local Agent LLM 端点与槽位绑定",
        default_msg_types=("llm_config_result",),
        icon="⚙️",
    ),
)

USER_UI = "user_ui"

_NAME_INDEX: dict[str, ModuleDef] = {}
for module in MODULES:
    for alias in module.names:
        _NAME_INDEX[alias] = module
    _NAME_INDEX[module.id] = module


def resolve_module(name: str, target: str | None = None) -> ModuleDef | None:
    if name == USER_UI and target:
        return _NAME_INDEX.get(target)
    return _NAME_INDEX.get(name)


def resolve_channel(name: str, target: str) -> str:
    """Return module id that owns this message in the UI."""
    if name == USER_UI:
        mod = _NAME_INDEX.get(target)
        return mod.id if mod else target
    mod = _NAME_INDEX.get(name)
    return mod.id if mod else name


def initial_status(msg_type: str) -> str:
    if msg_type == "approval_request":
        return "pending"
    return "delivered"


def module_to_dict(module: ModuleDef) -> dict:
    return {
        "id": module.id,
        "label": module.label,
        "names": list(module.names),
        "description": module.description,
        "default_msg_types": list(module.default_msg_types),
        "icon": module.icon,
    }
