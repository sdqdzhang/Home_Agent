from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DataBlock(BaseModel):
    """数据传输载体。id 由系统分配，不交给 LLM 生成。"""

    id: str = ""
    type: str = Field(..., description="内容类型，如 code / file；字符串宽松即可")
    content: str = Field(..., description="正文")
    producer: str = Field(..., description="生产者标识")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProcessRequest(BaseModel):
    requirement: str = Field(..., min_length=1, description="总要求")
    blocks: list[DataBlock] = Field(..., min_length=1, description="作为上下文的一到多个 DataBlock")
    request_id: str = ""


class ProcessResult(BaseModel):
    ok: bool
    requirement: str
    inputs: list[DataBlock] = Field(default_factory=list)
    output: DataBlock | None = None
    error: str = ""
    request_id: str = ""
