"""
SQLAlchemy declarative models for the app's OWNED runtime tables.

Scope note: the *starter data* tables (customers, orders, riders, restaurants,
complaints, refunds, reviews, rider_incidents, order_items) are read-only
snapshots loaded from `data/app.db` by `app/data_seed/bootstrap.py`. They are
intentionally NOT modeled here — repository.py accesses them via raw SQL,
which is the right shape for the pinned DATA_TODAY snapshot pattern.

The tables below are the ones the app *writes to* every turn (sessions,
turns, bot_executions) plus the new auth tables (users). These are the ones
Alembic manages and where the ORM layer adds real value (auth guards,
session ownership checks, etc.).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base for all owned-table models. Starter data tables are NOT declared
    here — they live under raw SQL in repository.py."""


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True,
    )


# ---------------------------------------------------------------------------
# Chat sessions (owned by users) + turns
#
# The name `ChatSession` intentionally avoids collision with the ORM's
# `Session`. Underlying table stays `sessions` for continuity with the
# existing raw-SQL code in phase3_handler / pipeline.
# ---------------------------------------------------------------------------


class ChatSession(Base):
    __tablename__ = "sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    # user_id is nullable so pre-auth sessions (existing prod-eval rows) survive
    # the migration cleanly. New sessions from the authenticated API layer
    # always populate it.
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    simulator_session_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True,
    )
    mode: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    scenario_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_turns: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    known_order_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    known_customer_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    close_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    final_score: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    user: Mapped[Optional["User"]] = relationship(back_populates="sessions")
    turns: Mapped[list["Turn"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Turn.id",
    )

    __table_args__ = (
        Index("ix_sessions_user_opened", "user_id", "opened_at"),
    )


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_no: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    classification: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    actions: Mapped[Optional[list | dict]] = mapped_column(JSONB, nullable=True)
    reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    route: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    escalation_group: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    execution_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    stage_timings_ms: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    session: Mapped["ChatSession"] = relationship(back_populates="turns")


class BotExecution(Base):
    __tablename__ = "bot_executions"

    execution_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    session_id: Mapped[Optional[str]] = mapped_column(
        String(64),
        ForeignKey("sessions.session_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    turn_no: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    escalation_group: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    priority: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
