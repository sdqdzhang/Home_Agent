from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator


class ExecuteRequest(BaseModel):
    """入口：明确的自然语言动作（非目标/需求）。"""

    action_text: str = Field(..., min_length=1)
    caller_module: str = "unknown"
    caller_request_id: str = ""
    purpose: str = ""
    file_content: str | None = None


class ShellRunAction(BaseModel):
    type: Literal["shell.run"] = "shell.run"
    command: str = Field(..., min_length=1)
    cwd: str | None = None
    timeout_seconds: int | None = None

    @field_validator("command")
    @classmethod
    def strip_command(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("command 不能为空")
        return text


class FileReadAction(BaseModel):
    type: Literal["file.read"] = "file.read"
    path: str = Field(..., min_length=1)
    encoding: str = "utf-8"


class FileWriteAction(BaseModel):
    type: Literal["file.write"] = "file.write"
    path: str = Field(..., min_length=1)
    content: str | None = None
    encoding: str = "utf-8"


ParsedAction = Annotated[
    ShellRunAction | FileReadAction | FileWriteAction,
    Field(discriminator="type"),
]


class ParseFailure(BaseModel):
    ok: Literal[False] = False
    error: Literal["not_executable"] = "not_executable"
    reason: str


class SecurityInfo(BaseModel):
    allowed: bool
    risk_level: str
    check_id: str
    reason: str = ""
    approval_id: str | None = None
    risk_source: str = "rule"


class ExecuteResult(BaseModel):
    ok: bool
    job_id: str | None = None
    error: str | None = None
    reason: str = ""
    action_type: str | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    files_touched: list[str] = Field(default_factory=list)
    security: SecurityInfo | None = None
    parsed_action: dict[str, Any] | None = None

    @classmethod
    def not_executable(cls, reason: str) -> ExecuteResult:
        return cls(ok=False, error="not_executable", reason=reason)

    @classmethod
    def security_denied(cls, job_id: str, reason: str, security: SecurityInfo) -> ExecuteResult:
        return cls(
            ok=False,
            job_id=job_id,
            error="security_denied",
            reason=reason,
            security=security,
        )

    @classmethod
    def cancelled(cls, job_id: str, reason: str = "用户已终止执行") -> ExecuteResult:
        return cls(ok=False, job_id=job_id, error="cancelled", reason=reason)
