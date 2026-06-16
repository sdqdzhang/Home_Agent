from typing import Any

from pydantic import BaseModel, Field


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
    encrypted: str | None = None
    encrypted_chunks: list[str] | None = None


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
