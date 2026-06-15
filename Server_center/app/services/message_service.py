import json
from typing import Any

from app.modules import USER_UI, initial_status, resolve_channel, resolve_module
from app.models.db import ClientRecord, MessageRecord, SessionLocal, record_to_dict, utc_now
from app.models.message import InboundMessage, ResponseBody
from app.services.ws_manager import ws_manager


class MessageService:
    def __init__(self) -> None:
        self._private_key = None
        self._public_key = None

    def set_keys(self, private_key, public_key) -> None:
        self._private_key = private_key
        self._public_key = public_key

    def create_message(self, msg: InboundMessage) -> dict[str, Any]:
        now = utc_now()
        channel = resolve_channel(msg.name, msg.target)
        status = initial_status(msg.msg_type)

        with SessionLocal() as db:
            existing = db.get(MessageRecord, msg.id)
            if existing:
                raise ValueError(f"Message id already exists: {msg.id}")

            record = MessageRecord(
                id=msg.id,
                name=msg.name,
                target=msg.target,
                msg_type=msg.msg_type,
                message_json=json.dumps(msg.message, ensure_ascii=False),
                timestamp=msg.timestamp,
                status=status,
                response_json=None,
                created_at=now,
                updated_at=now,
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            data = record_to_dict(record)

        data["channel"] = channel
        if resolve_module(msg.name, msg.target) is None and msg.name != USER_UI:
            data["unknown_module"] = msg.name

        ws_manager.broadcast(msg.target, {"event": "new_message", "data": data})
        if channel and channel != msg.target:
            ws_manager.broadcast(channel, {"event": "new_message", "data": data})
        return data

    def list_messages(
        self,
        target: str | None = None,
        name: str | None = None,
        status: str | None = None,
        msg_type: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        with SessionLocal() as db:
            query = db.query(MessageRecord)
            if target:
                query = query.filter(MessageRecord.target == target)
            if name:
                query = query.filter(MessageRecord.name == name)
            if status:
                query = query.filter(MessageRecord.status == status)
            if msg_type:
                query = query.filter(MessageRecord.msg_type == msg_type)
            records = query.order_by(MessageRecord.created_at.desc()).limit(limit).all()
            return [record_to_dict(r) for r in records]

    def get_message(self, message_id: str) -> dict[str, Any] | None:
        with SessionLocal() as db:
            record = db.get(MessageRecord, message_id)
            if not record:
                return None
            return record_to_dict(record)

    def respond(self, response: ResponseBody) -> dict[str, Any]:
        now = utc_now()
        with SessionLocal() as db:
            record = db.get(MessageRecord, response.ref_id)
            if not record:
                raise ValueError(f"Message not found: {response.ref_id}")
            if record.status != "pending":
                raise ValueError(f"Message already handled: {response.ref_id}")

            approved = response.message.get("approved")
            if response.msg_type == "approval_response" and isinstance(approved, bool):
                record.status = "approved" if approved else "rejected"
            else:
                record.status = "handled"

            record.response_json = json.dumps(response.message, ensure_ascii=False)
            record.updated_at = now
            db.commit()
            db.refresh(record)
            data = record_to_dict(record)

        data["channel"] = resolve_channel(record.name, record.target)
        ws_manager.broadcast(record.target, {"event": "message_updated", "data": data})
        ws_manager.broadcast(record.name, {"event": "response_ready", "data": data})
        if data["channel"] not in (record.target, record.name):
            ws_manager.broadcast(data["channel"], {"event": "message_updated", "data": data})
        return data

    def register_client(self, client_id: str, public_key_pem: str) -> dict[str, str]:
        now = utc_now()
        with SessionLocal() as db:
            record = db.get(ClientRecord, client_id)
            if record:
                record.public_key_pem = public_key_pem
                record.registered_at = now
            else:
                record = ClientRecord(
                    client_id=client_id,
                    public_key_pem=public_key_pem,
                    registered_at=now,
                )
                db.add(record)
            db.commit()
        return {"client_id": client_id, "status": "registered"}

    def get_client_public_key(self, client_id: str) -> str | None:
        with SessionLocal() as db:
            record = db.get(ClientRecord, client_id)
            if not record:
                return None
            return record.public_key_pem

    def encrypt_for_client(self, client_id: str, payload: dict[str, Any]) -> str | None:
        from app.crypto.rsa import encrypt_to_b64, load_public_key_from_pem

        pem = self.get_client_public_key(client_id)
        if not pem:
            return None
        public_key = load_public_key_from_pem(pem)
        raw = json.dumps(payload, ensure_ascii=False).encode()
        return encrypt_to_b64(raw, public_key)


message_service = MessageService()
