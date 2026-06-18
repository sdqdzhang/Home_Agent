from __future__ import annotations

from shared.llm.schemas import SlotDefinition

DEFAULT_CHAT_SLOT = "default.chat"

SLOT_DEFINITIONS: tuple[SlotDefinition, ...] = (
    SlotDefinition(
        slot_key=DEFAULT_CHAT_SLOT,
        label="默认 Chat",
        module="shared",
        capability="chat",
        description="未单独配置的 Chat 槽位回退目标",
    ),
    SlotDefinition(
        slot_key="rag.summarize",
        label="RAG 问答总结",
        module="rag",
        capability="chat",
        description="检索后由模型阅读片段并生成回答",
    ),
    SlotDefinition(
        slot_key="rag.split",
        label="RAG 语义分块",
        module="rag",
        capability="chat",
        description="判断相邻文本是否应切分为新块",
    ),
    SlotDefinition(
        slot_key="rag.embed",
        label="RAG 向量化",
        module="rag",
        capability="embed",
        description="文档入库时的 embedding 模型",
    ),
    SlotDefinition(
        slot_key="crawler.pipeline",
        label="爬虫流水线",
        module="crawler",
        capability="chat",
        description="爬取判断、调参、过滤器择优等",
    ),
    SlotDefinition(
        slot_key="crawler.chat",
        label="爬虫对话",
        module="crawler",
        capability="chat",
        description="爬虫模块用户对话",
    ),
    SlotDefinition(
        slot_key="env.summary",
        label="环境周期总结",
        module="env",
        capability="chat",
        description="监控窗口数据的 LLM 总结与告警",
    ),
    SlotDefinition(
        slot_key="env.chat",
        label="环境问答",
        module="env",
        capability="chat",
        description="基于系统状态回答用户问题",
    ),
    SlotDefinition(
        slot_key="security.judge",
        label="安全黄色升红",
        module="security",
        capability="chat",
        description="黄色命令是否升级为红色审批",
    ),
    SlotDefinition(
        slot_key="security.chat",
        label="安全对话",
        module="security",
        capability="chat",
        description="安全检查模块用户问答",
    ),
    SlotDefinition(
        slot_key="security.auto_approve",
        label="安全自动审批",
        module="security",
        capability="chat",
        description="模型代替用户审批红色命令",
    ),
)

SLOT_BY_KEY: dict[str, SlotDefinition] = {item.slot_key: item for item in SLOT_DEFINITIONS}


def is_valid_slot(slot_key: str) -> bool:
    return slot_key in SLOT_BY_KEY


def get_slot(slot_key: str) -> SlotDefinition:
    from shared.llm.errors import InvalidSlotError

    if slot_key not in SLOT_BY_KEY:
        raise InvalidSlotError(slot_key)
    return SLOT_BY_KEY[slot_key]
