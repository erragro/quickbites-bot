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

from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, backref, mapped_column, relationship


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
    # Super-admin bypasses per-module ACL and can manage users + module
    # registrations. Kept separate from `user_module_access` so bootstrap
    # doesn't need a self-referential grant (chicken-and-egg on first user).
    is_super_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, index=True,
    )
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
    # `foreign_keys` disambiguates the two FKs from user_module_access →
    # users (owner via user_id, and audit trail via granted_by).
    module_accesses: Mapped[list["UserModuleAccess"]] = relationship(
        back_populates="user",
        foreign_keys="UserModuleAccess.user_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    uploaded_contracts: Mapped[list["UploadedContract"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="UploadedContract.created_at.desc()",
    )


# ---------------------------------------------------------------------------
# Module registry — one row per feature module the platform exposes.
# ---------------------------------------------------------------------------


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    path: Mapped[str] = mapped_column(String(100), nullable=False)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    accesses: Mapped[list["UserModuleAccess"]] = relationship(
        back_populates="module",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class UserModuleAccess(Base):
    __tablename__ = "user_module_access"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    module_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("modules.id", ondelete="CASCADE"),
        nullable=False,
    )
    access_level: Mapped[str] = mapped_column(String(20), nullable=False)
    granted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    user: Mapped["User"] = relationship(
        back_populates="module_accesses",
        foreign_keys=[user_id],
    )
    module: Mapped["Module"] = relationship(back_populates="accesses")

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "module_id", name="pk_user_module_access"),
        CheckConstraint(
            "access_level IN ('view','edit','admin')",
            name="ck_user_module_access_level",
        ),
        Index("ix_user_module_access_module", "module_id"),
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
    # Set the moment a customer taps a chip; persists so every subsequent
    # turn in the session knows which issue-type contract to enrich
    # against. Nullable — a free-text-first session may never carry one.
    issue_type_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issue_types.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    business_unit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_units.id", ondelete="SET NULL"),
        nullable=True,
    )

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


# ---------------------------------------------------------------------------
# Conversation Studio — config-driven chip-tap chatbot.
#
# BusinessUnit → IssueType is a tree (top-level BUs are hierarchical if
# ever needed via parent_id). Each IssueType declares which data points
# the enricher must fetch when the customer taps it, and carries multiple
# acknowledgment templates whose {{variable}} slots are filled from the
# enriched context blob. `routes_to_intent` binds the admin-facing name
# back to the existing Stage 2 matrix so the deterministic policy layer
# stays untouched.
# ---------------------------------------------------------------------------


class BusinessUnit(Base):
    __tablename__ = "business_units"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_units.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    # Self-referential parent ↔ children. `remote_side="BusinessUnit.id"`
    # on the parent backref tells SQLAlchemy which end is the "one" side.
    children: Mapped[list["BusinessUnit"]] = relationship(
        "BusinessUnit",
        cascade="all, delete-orphan",
        passive_deletes=True,
        backref=backref("parent", remote_side="BusinessUnit.id"),
    )
    issue_types: Mapped[list["IssueType"]] = relationship(
        back_populates="business_unit",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="IssueType.sort_order",
    )


class DataPoint(Base):
    """Registry of Python fetchers exposed to the admin panel by key.

    Admin CAN'T register new fetchers through the API — those are code
    (see app/conversation_studio/service.py::FETCHER_REGISTRY). They can
    only pick from the ones already registered. Prevents arbitrary code
    execution while still giving them full control over per-issue-type
    data contracts.
    """

    __tablename__ = "data_point_registry"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    fetcher_ref: Mapped[str] = mapped_column(String(150), nullable=False)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class IssueType(Base):
    __tablename__ = "issue_types"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    business_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("business_units.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    routes_to_intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    business_unit: Mapped["BusinessUnit"] = relationship(back_populates="issue_types")
    data_point_links: Mapped[list["IssueTypeDataPoint"]] = relationship(
        back_populates="issue_type",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="IssueTypeDataPoint.sort_order",
    )
    templates: Mapped[list["AcknowledgmentTemplate"]] = relationship(
        back_populates="issue_type",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("business_unit_id", "code", name="uq_issue_types_bu_code"),
        Index("ix_issue_types_routed_intent", "routes_to_intent"),
    )


class IssueTypeDataPoint(Base):
    __tablename__ = "issue_type_data_points"

    issue_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issue_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    data_point_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_point_registry.id", ondelete="RESTRICT"),
        nullable=False,
    )
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)

    issue_type: Mapped["IssueType"] = relationship(back_populates="data_point_links")
    data_point: Mapped["DataPoint"] = relationship()

    __table_args__ = (
        PrimaryKeyConstraint(
            "issue_type_id", "data_point_id", name="pk_issue_type_data_points",
        ),
    )


class AcknowledgmentTemplate(Base):
    __tablename__ = "acknowledgment_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    issue_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issue_types.id", ondelete="CASCADE"),
        nullable=False,
    )
    template: Mapped[str] = mapped_column(Text, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )

    issue_type: Mapped["IssueType"] = relationship(back_populates="templates")

    __table_args__ = (
        Index(
            "ix_ack_templates_issue_type", "issue_type_id", "is_active",
        ),
    )


class IntentDetectionCase(Base):
    """
    Grows into the training set for a distilled deterministic intent
    classifier. Every free-text turn adds a row; over time the library
    replaces the LLM-based Stage 0 on the hot path (see design memo).
    """

    __tablename__ = "intent_detection_cases"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    customer_message: Mapped[str] = mapped_column(Text, nullable=False)
    matched_issue_type_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("issue_types.id", ondelete="SET NULL"),
        nullable=True,
    )
    # "rule" | "llm" | "human_verified"
    matched_by: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(4, 3), nullable=True,
    )
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    seen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("ix_intent_cases_lookup", "matched_issue_type_id", "matched_by"),
    )


# ---------------------------------------------------------------------------
# Sreshtha content model — Rights Guide, Schemes, Complaints, Contracts.
#
# fact_cards + complaint_templates: one row per (topic_key, language). The
# card/template is fully language-scoped because the *content itself* is
# what changes across languages, not just the display labels.
#
# schemes + scheme_translations: split. Eligibility rules stay canonical
# in `schemes` (matching by state + occupation joins one table); localised
# copy lives in `scheme_translations` (one row per language).
#
# uploaded_contracts: per-user file uploads with a status-machine that
# advances from 'uploaded' → 'ocr_done' → 'ready' as the three-stage
# processor works through it. The `stages` JSONB holds the accumulating
# output; shape is documented in the migration comments.
#
# Every content row has a nullable `tenant_id` for future multi-tenancy.
# NULL means shared (v1 default). See docs/PRD.md § 7.
# ---------------------------------------------------------------------------


class FactCard(Base):
    """One row per (topic_key, language). All variants of the same fact
    (Hindi, Bengali, Tamil, English) share the topic_key. UI resolves
    which row to show by (topic_key, user_language) lookup."""

    __tablename__ = "fact_cards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    topic_key: Mapped[str] = mapped_column(String(80), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    citation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    action_steps: Mapped[Optional[list | dict]] = mapped_column(JSONB, nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Pre-generated TTS URL from Sarvam. Null → render on-demand.
    audio_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "topic_key", "language", "tenant_id",
            name="uq_fact_cards_topic_lang_tenant",
        ),
        CheckConstraint(
            "language IN ('en','hi','bn','ta','te','kn','mr')",
            name="ck_fact_cards_language",
        ),
        Index("ix_fact_cards_lang_active", "language", "is_active"),
        Index("ix_fact_cards_topic", "topic_key"),
        Index("ix_fact_cards_tenant", "tenant_id"),
    )


class Scheme(Base):
    """Government scheme metadata. Language-agnostic. Translations live
    in scheme_translations."""

    __tablename__ = "schemes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    # 'central', 'all', or a state code like 'karnataka'
    state_scope: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # Structured eligibility rules — see migration 005 comment for shape.
    # Schemes Finder walks this dict against the user's profile.
    eligibility_rules: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
    )
    apply_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # Array of {name, note?}
    docs_needed: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    estimated_time: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    icon: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    translations: Mapped[list["SchemeTranslation"]] = relationship(
        back_populates="scheme",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        UniqueConstraint("key", "tenant_id", name="uq_schemes_key_tenant"),
        Index("ix_schemes_state_active", "state_scope", "is_active"),
        Index("ix_schemes_tenant", "tenant_id"),
    )


class SchemeTranslation(Base):
    __tablename__ = "scheme_translations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    scheme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("schemes.id", ondelete="CASCADE"),
        nullable=False,
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    apply_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    scheme: Mapped["Scheme"] = relationship(back_populates="translations")

    __table_args__ = (
        UniqueConstraint(
            "scheme_id", "language", name="uq_scheme_translations_scheme_lang",
        ),
        CheckConstraint(
            "language IN ('en','hi','bn','ta','te','kn','mr')",
            name="ck_scheme_translations_language",
        ),
        Index("ix_scheme_translations_lang", "language"),
    )


class ComplaintTemplate(Base):
    """One row per (topic_key, language). Body carries {{variable}}
    placeholders filled from the required_fields form at render time
    (existing Handlebars-style renderer)."""

    __tablename__ = "complaint_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    topic_key: Mapped[str] = mapped_column(String(80), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Escalation ladder — see migration 005 for shape.
    routing: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Form fields the worker fills — see migration 005 for shape.
    required_fields: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "topic_key", "language", "tenant_id",
            name="uq_complaint_templates_topic_lang_tenant",
        ),
        CheckConstraint(
            "language IN ('en','hi','bn','ta','te','kn','mr')",
            name="ck_complaint_templates_language",
        ),
        Index("ix_complaint_templates_lang_active", "language", "is_active"),
        Index("ix_complaint_templates_topic", "topic_key"),
    )


class UploadedContract(Base):
    """Per-user contract file with its three-stage processing state.

    Status machine (enforced by CHECK constraint in migration):
      uploaded → ocr_pending → ocr_done → processing → ready
                                                    ↓
                                                  failed
    The `stages` JSONB accumulates output from each stage; consumers can
    render whatever's ready (e.g. show OCR text while stages 2-3 run)."""

    __tablename__ = "uploaded_contracts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="uploaded")
    ocr_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # {stage_1: {...}, stage_2: {...}, stage_3: {...}} — shape doc in migration
    stages: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Detected language of the contract source (from OCR). Not user-facing
    # by itself; used to hint Stage 1 clause extraction.
    language: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # Worker's chosen OUTPUT language. Set at upload time. Stage 3 renders
    # explanations/implications/actions in this language regardless of the
    # contract's source language (many workers can't read English contracts
    # but need the analysis in Hindi/Bengali/Tamil).
    target_language: Mapped[str] = mapped_column(
        String(10), nullable=False, default="en",
    )
    # 'native' or 'roman'. When 'roman' and target_language != 'en', the
    # Day-13 transliteration pass converts the native-script Stage 3
    # output to Latin letters (aap ek swatantra thekedaar hain vs
    # आप एक स्वतंत्र ठेकेदार हैं).
    target_script: Mapped[str] = mapped_column(
        String(10), nullable=False, default="native",
    )
    # Sarvam Mayura's tone/register mode — worker's choice for how
    # "English-y" the translation should feel. Values:
    #   formal              polite standard tone (default)
    #   modern-colloquial   casual, some English loanwords retained
    #   classic-colloquial  traditional spoken style
    #   code-mixed          heavy Hinglish/Benglish
    # Passed through to Mayura's `mode` parameter on every call.
    translation_mode: Mapped[str] = mapped_column(
        String(30), nullable=False, default="formal",
    )
    contract_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    user: Mapped["User"] = relationship(back_populates="uploaded_contracts")

    __table_args__ = (
        CheckConstraint(
            "status IN ('uploaded','ocr_pending','ocr_done','processing','ready','failed')",
            name="ck_uploaded_contracts_status",
        ),
        Index(
            "ix_uploaded_contracts_user_created", "user_id", "created_at",
        ),
        Index("ix_uploaded_contracts_status", "status"),
    )


# ---------------------------------------------------------------------------
# Idiom library — deterministic phrase-level translations
#
# Runtime scans English source text (Stage 3 output, chatbot responses,
# fact cards) for known idioms via Aho-Corasick (see app/translate/idioms.py)
# and swaps them for pre-verified target-language equivalents before + after
# the general-purpose Mayura translation. Editing lives in the admin panel;
# every write invalidates the runtime automaton cache.
# ---------------------------------------------------------------------------


class Idiom(Base):
    """English source phrase + its meaning gloss. Translations live in
    IdiomTranslation, one row per language."""

    __tablename__ = "idiom_library"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    source_phrase: Mapped[str] = mapped_column(String(200), nullable=False)
    meaning: Mapped[str] = mapped_column(Text, nullable=False)
    # 'legal' | 'work' | 'money' | 'general' | 'safety' — enforced by the
    # DB check constraint in migration 007. Kept as a plain string here
    # so admins can extend categories later without a schema change (we'd
    # just relax the check).
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tenant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    translations: Mapped[list["IdiomTranslation"]] = relationship(
        back_populates="idiom",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="IdiomTranslation.language",
    )

    __table_args__ = (
        UniqueConstraint(
            "source_phrase", "tenant_id",
            name="uq_idiom_library_phrase_tenant",
        ),
        CheckConstraint(
            "category IN ('legal','work','money','general','safety')",
            name="ck_idiom_library_category",
        ),
    )


class IdiomTranslation(Base):
    __tablename__ = "idiom_translations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
    )
    idiom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("idiom_library.id", ondelete="CASCADE"),
        nullable=False,
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    translation: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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

    idiom: Mapped["Idiom"] = relationship(back_populates="translations")

    __table_args__ = (
        UniqueConstraint(
            "idiom_id", "language",
            name="uq_idiom_translations_idiom_lang",
        ),
        CheckConstraint(
            "language IN ('en','hi','bn','ta','te','kn','mr')",
            name="ck_idiom_translations_language",
        ),
    )
