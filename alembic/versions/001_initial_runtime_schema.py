"""initial runtime schema (sessions, turns, bot_executions)

Revision ID: 001
Revises:
Create Date: 2026-04-26

Matches the DDL that used to live in app/migrations/bootstrap.py.
Kept in Alembic so schema evolution has a single source of truth.

For pre-existing deployments where these tables were created by the old
bootstrap.py, the startup path stamps them at revision 001 and then
upgrades forward — no data loss, no duplicate CREATE errors.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(length=64), primary_key=True),
        sa.Column("simulator_session_id", sa.String(length=64), unique=True),
        sa.Column("mode", sa.String(length=20)),
        sa.Column("scenario_id", sa.Integer()),
        sa.Column("max_turns", sa.Integer()),
        sa.Column("known_order_id", sa.Integer()),
        sa.Column("known_customer_id", sa.Integer()),
        sa.Column(
            "opened_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("close_reason", sa.Text()),
        sa.Column("final_score", postgresql.JSONB(astext_type=sa.Text())),
    )

    op.create_table(
        "turns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "session_id",
            sa.String(length=64),
            sa.ForeignKey("sessions.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("turn_no", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text()),
        sa.Column("classification", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("actions", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("reasoning", sa.Text()),
        sa.Column("route", sa.String(length=50)),
        sa.Column("escalation_group", sa.String(length=50)),
        sa.Column("execution_id", sa.String(length=100)),
        sa.Column("stage_timings_ms", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_turns_session_id", "turns", ["session_id"])

    op.create_table(
        "bot_executions",
        sa.Column("execution_id", sa.String(length=100), primary_key=True),
        sa.Column(
            "session_id",
            sa.String(length=64),
            sa.ForeignKey("sessions.session_id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("turn_no", sa.Integer()),
        sa.Column("escalation_group", sa.String(length=50)),
        sa.Column("priority", sa.String(length=20)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_bot_executions_session_id", "bot_executions", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_bot_executions_session_id", table_name="bot_executions")
    op.drop_table("bot_executions")
    op.drop_index("ix_turns_session_id", table_name="turns")
    op.drop_table("turns")
    op.drop_table("sessions")
