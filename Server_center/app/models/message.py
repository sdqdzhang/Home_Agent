from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MessageBody(BaseModel):
    text: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class InboundMessage(BaseModel):
    id: str
    name: str
    target: str
    msg_type: str
    message: dict[str, Any]
    timestamp: int


class EncryptedPayload(BaseModel):
    """RSA-OAEP chunks (legacy) or hybrid RSA-OAEP+AES-GCM (v=1)."""

    model_config = ConfigDict(extra="ignore")

    encrypted: str | None = None
    encrypted_chunks: list[str] | None = None
    v: int | None = None
    alg: str | None = None
    ek: str | None = None
    iv: str | None = None
    ct: str | None = None


class ResponseBody(BaseModel):
    ref_id: str
    msg_type: str
    message: dict[str, Any]
    timestamp: int


class ClientRegistration(BaseModel):
    client_id: str
    public_key: str


class ApprovalResponseMessage(BaseModel):
    approved: bool
    reason: str = ""


class MessageUpdateBody(BaseModel):
    """原地更新消息内容（用于规划会话卡等可演化消息）。"""

    message: dict[str, Any] | None = None
    status: str | None = None
    timestamp: int | None = None
