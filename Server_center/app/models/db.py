from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    pass


class MessageRecord(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    target: Mapped[str] = mapped_column(String(128), index=True)
    msg_type: Mapped[str] = mapped_column(String(64), index=True)
    message_json: Mapped[str] = mapped_column(Text)
    timestamp: Mapped[int] = mapped_column()
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    response_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClientRecord(Base):
    __tablename__ = "clients"

    client_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    public_key_pem: Mapped[str] = mapped_column(Text)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


settings.data_dir.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{settings.db_path}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def record_to_dict(record: MessageRecord) -> dict[str, Any]:
    import json

    return {
        "id": record.id,
        "name": record.name,
        "target": record.target,
        "msg_type": record.msg_type,
        "message": json.loads(record.message_json),
        "timestamp": record.timestamp,
        "status": record.status,
        "response": json.loads(record.response_json) if record.response_json else None,
        "created_at": record.created_at.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }
