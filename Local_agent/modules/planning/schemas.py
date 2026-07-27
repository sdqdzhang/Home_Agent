from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from modules.processor.schemas import DataBlock

# body: 写入附件正文（Action，通常恰好 1 个）
# context: 仅依赖/排队，不进附件（如 directory）
# requirement: 处理规格（Process 至少 1 个）
# material: 处理参考材料（Process）
InputRole = Literal["body", "context", "requirement", "material"]

ACTION_INPUT_ROLES = frozenset({"body", "context"})
PROCESS_INPUT_ROLES = frozenset({"requirement", "material", "context"})


class NodeInput(BaseModel):
    """消费前置节点产出的 DataBlock（只声明输入 + 角色）。"""

    model_config = {"populate_by_name": True}

    from_node: str = Field(
        ...,
        alias="from",
        min_length=1,
        description="前置节点 id，或固定起点 goal",
    )
    role: InputRole = Field(
        ...,
        description="body|context|requirement|material",
    )


class NodeOutputSpec(BaseModel):
    """规划期声明的产出类型；content / path 由运行时填充。"""

    type: str = Field(..., min_length=1, description="如 goal/code/directory/file/text/requirement")

    @field_validator("type")
    @classmethod
    def strip_type(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("output.type 不能为空")
        return text


class ActionNode(BaseModel):
    """执行节点：自然语言指令 → executor；必须产出一个 DataBlock。"""

    id: str = Field(..., min_length=1)
    kind: Literal["action"] = "action"
    instruction: str = Field(..., min_length=1, description="交给 executor 的自然语言动作（路径用绝对路径）")
    inputs: list[NodeInput] = Field(default_factory=list)
    output: NodeOutputSpec = Field(..., description="本节点产出的 DataBlock 类型声明")

    @field_validator("id", "instruction")
    @classmethod
    def strip_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("不能为空")
        return text


class ProcessNode(BaseModel):
    """处理节点：短操作说明 + 带 role 的输入块 → 一个输出 DataBlock。

    requirement 只写操作句（如「根据附件的代码要求写代码」）；
    真正规格放在 role=requirement 的输入块中。
    """

    id: str = Field(..., min_length=1)
    kind: Literal["process"] = "process"
    requirement: str = Field(..., min_length=1, description="短操作说明，规格在 requirement 输入块里")
    inputs: list[NodeInput] = Field(default_factory=list)
    output: NodeOutputSpec = Field(..., description="期望产出类型")

    @field_validator("id", "requirement")
    @classmethod
    def strip_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("不能为空")
        return text


PlanNode = Annotated[ActionNode | ProcessNode, Field(discriminator="kind")]


class TaskGraph(BaseModel):
    """静态任务图：仅含 ActionNode / ProcessNode；边由 DataBlock 消费关系导出。"""

    summary: str = ""
    nodes: list[PlanNode] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> TaskGraph:
        seen: set[str] = set()
        for node in self.nodes:
            if node.id in seen:
                raise ValueError(f"重复的节点 id: {node.id!r}")
            seen.add(node.id)
        return self


class ClarifyQuestion(BaseModel):
    """一轮质询中的单题（调用方负责展示选项并收集回答）。"""

    id: str = Field(..., min_length=1)
    prompt: str = Field(..., min_length=1)
    reason: str = ""
    choices: list[str] = Field(..., min_length=1, description="可选答案；UI 应追加「其他」")

    @field_validator("choices")
    @classmethod
    def strip_choices(cls, value: list[str]) -> list[str]:
        cleaned = [c.strip() for c in value if str(c).strip()]
        if not cleaned:
            raise ValueError("choices 不能为空")
        return cleaned


class ClarifyAnswer(BaseModel):
    question_id: str
    answer: str
    question: str = Field(default="", description="问题原文，便于合成有效目标与提示词")


def compose_goal(goal: str, clarifications: list["ClarifyAnswer"]) -> str:
    """把原始目标与澄清 Q/A 合成为「有效目标」；规划与运行时 GoalBlock 都用它。"""
    base = (goal or "").strip()
    items = [c for c in clarifications if (c.answer or "").strip()]
    if not items:
        return base
    lines = [base, "", "## 澄清补充"]
    for c in items:
        label = (c.question or c.question_id or "").strip()
        answer = c.answer.strip()
        lines.append(f"- {label}：{answer}" if label else f"- {answer}")
    return "\n".join(lines)


class EnvQuery(BaseModel):
    """环境探测请求：一句只读自然语言，交给 Executor（经 Security）执行。"""

    id: str = Field(..., min_length=1)
    instruction: str = Field(..., min_length=1, description="只读探测指令：浏览目录/读文件/搜索等")
    purpose: str = Field(default="", description="为何需要这条环境事实")

    @field_validator("id", "instruction")
    @classmethod
    def strip_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("不能为空")
        return text


EnvProbeStatus = Literal["succeeded", "failed", "denied_user", "denied_security"]


class EnvProbeRecord(BaseModel):
    """一条环境探测的结果状态，回传给规划（避免重复请求）。

    成功时 block_id 指向对应的初始 DataBlock；失败/拒绝不产生 DataBlock。
    """

    id: str
    instruction: str
    purpose: str = ""
    status: EnvProbeStatus
    block_id: str = ""
    summary: str = Field(default="", description="内容摘要或失败原因")
    round_index: int = 1


class ClarifyRequest(BaseModel):
    """信息收集一轮请求（调用方维护 history / env_records / round_index）。"""

    goal: str = Field(..., min_length=1)
    history: list[ClarifyAnswer] = Field(default_factory=list)
    env_records: list[EnvProbeRecord] = Field(default_factory=list)
    round_index: int = 1


class ClarifyOutcome(BaseModel):
    """信息收集一轮的返回：用户质询 + 环境探测；或已可进入规划。

    ready=false 时至少要有 questions 或 env_queries 之一（不强迫两者都有）。
    """

    ready: bool
    questions: list[ClarifyQuestion] = Field(default_factory=list)
    env_queries: list[EnvQuery] = Field(default_factory=list)
    note: str = ""

    @model_validator(mode="after")
    def check_requests(self) -> ClarifyOutcome:
        if not self.ready and not self.questions and not self.env_queries:
            raise ValueError("ready=false 时必须至少提供 questions 或 env_queries")
        return self


class PlanRequest(BaseModel):
    """出图请求：目标 + 澄清答案 + 环境初始块。"""

    goal: str = Field(..., min_length=1)
    clarifications: list[ClarifyAnswer] = Field(default_factory=list)
    context_blocks: list[DataBlock] = Field(
        default_factory=list, description="环境探测得到的初始块，规划可引用（from=env*）"
    )


class PlanOutcome(BaseModel):
    """出图结果；ok 时 graph 为校验通过的 TaskGraph。"""

    ok: bool
    graph: TaskGraph | None = None
    error: str = ""
    raw: dict[str, Any] | None = None


class NodeRunStatus(BaseModel):
    node_id: str
    status: Literal["pending", "running", "succeeded", "failed", "skipped"] = "pending"
    attempts: int = 0
    error: str = ""
    output_block_id: str | None = None
    action_type: str | None = None


class GraphRunResult(BaseModel):
    """任务图拓扑执行结果。"""

    ok: bool
    goal: str
    summary: str = ""
    nodes: list[NodeRunStatus] = Field(default_factory=list)
    blocks: list[dict[str, Any]] = Field(default_factory=list)
    error: str = ""
    skipped_node_ids: list[str] = Field(default_factory=list)
