"""SQLAlchemy ORM models — mirror db/init.sql tables."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, JSON, Boolean, DateTime, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Audit(Base):
    __tablename__ = "audits"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    agent_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    action_assessed: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(String(16), nullable=False)
    overall_score: Mapped[float] = mapped_column(Numeric(4, 2), nullable=False)
    virtues: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    delta: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    trend: Mapped[str] = mapped_column(String(16), nullable=False, default="UNKNOWN")
    bridge_compliant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requires_human_approval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    stoic_feedback: Mapped[str] = mapped_column(Text, nullable=False)
    raw_gemini_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemoryExport(Base):
    __tablename__ = "memory_exports"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    memory_id: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    source: Mapped[str] = mapped_column(String, nullable=False)
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String).with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    total_messages: Mapped[int] = mapped_column(nullable=False)
    conversation: Mapped[list[dict]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"), nullable=False
    )
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
