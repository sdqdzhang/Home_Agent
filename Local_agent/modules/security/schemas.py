from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["green", "yellow", "red"]


class CheckRequest(BaseModel):
    command: str = Field(..., min_length=1)
    purpose: str = ""
    caller_module: str = "unknown"
    caller_request_id: str = ""


class CheckResult(BaseModel):
    allowed: bool
    risk_level: RiskLevel
    check_id: str
    reason: str = ""
    approval_id: str | None = None
    risk_source: Literal["rule", "model", "user", "timeout"] = "rule"


class RuleEvaluation(BaseModel):
    risk_level: RiskLevel
    reason: str
    matched_white_command: bool = False
    matched_black_command: bool = False
    black_directories: list[str] = Field(default_factory=list)
    white_directories_only: bool = False
    extracted_paths: list[str] = Field(default_factory=list)
