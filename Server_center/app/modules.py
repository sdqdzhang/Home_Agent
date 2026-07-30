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
        id="main",
        label="主对话",
        names=("main", "主对话"),
        description="主对话：聊天 + Function Calling 编排（规划/执行/RAG/环境/扩展）",
        default_msg_types=("text", "tool_result", "plan_result", "clarify_result", "plan_progress", "graph_run_result"),
        icon="◉",
    ),
    ModuleDef(
        id="conversation_manager",
        label="会话管理",
        names=("会话管理", "conversation_manager", "cm"),
        description="会话生命周期：规则触发 Analyzer、Conversation State、记忆候选与指标",
        default_msg_types=("cm_snapshot", "cm_event", "text"),
        icon="☰",
    ),
    ModuleDef(
        id="planning",
        label="规划",
        names=("规划模块", "planning", "planner"),
        description="目标→质询/环境探测→TaskGraph→拓扑执行",
        default_msg_types=(
            "plan_result",
            "clarify_result",
            "env_probe_result",
            "plan_progress",
            "graph_run_result",
            "text",
        ),
        icon="◎",
    ),
    ModuleDef(
        id="emotion",
        label="情感与状态",
        names=("情感与性格状态模块", "emotion", "persona"),
        description="情感、性格与情绪状态的感知与表达",
        default_msg_types=("persona_state", "text"),
        icon="◌",
    ),
    ModuleDef(
        id="security",
        label="安全检查",
        names=("安全检查模块", "security"),
        description="危险操作审批与安全策略校验",
        default_msg_types=("approval_request", "security_yellow_log", "text"),
        icon="⛨",
    ),
    ModuleDef(
        id="env",
        label="环境感知",
        names=("环境感知模块", "env_sense", "env"),
        description="系统采集与摘要；主对话仅在主动工具调用时展示结果",
        default_msg_types=("system_status", "desktop_screenshot", "camera_capture"),
        icon="◈",
    ),
    ModuleDef(
        id="memory",
        label="记忆",
        names=("记忆模块", "memory"),
        description="记忆的写入、检索、压缩与反思",
        default_msg_types=("memory_record", "text"),
        icon="◫",
    ),
    ModuleDef(
        id="crawler",
        label="网页爬取",
        names=("网页爬取模块", "crawler"),
        description="网页抓取任务与结果日志（主对话扩展工具）",
        default_msg_types=("execution_log",),
        icon="◍",
    ),
    ModuleDef(
        id="rag",
        label="RAG",
        names=("RAG模块", "RAG 模块", "rag"),
        description="检索增强生成：查询、召回与回答",
        default_msg_types=("rag_result", "text"),
        icon="◬",
    ),
    ModuleDef(
        id="executor",
        label="执行",
        names=("执行模块", "executor", "execution"),
        description="自然语言自动路由：命令 / 文件操作",
        default_msg_types=("execution_log",),
        icon="▶",
    ),
    ModuleDef(
        id="processor",
        label="处理",
        names=("处理", "processor"),
        description="要求 + DataBlock 上下文 → 产出一个 DataBlock",
        default_msg_types=("datablock", "text"),
        icon="▦",
    ),
    ModuleDef(
        id="llm",
        label="模型配置",
        names=("本地Agent", "local_agent", "llm"),
        description="Local Agent LLM 端点与槽位绑定",
        default_msg_types=("llm_config_result",),
        icon="⎇",
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
