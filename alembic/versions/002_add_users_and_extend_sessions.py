"""add users table + extend sessions with user_id and title

Revision ID: 002
Revises: 001
Create Date: 2026-04-26

Adds the auth layer's users table and hangs sessions off it so every chat
session has an owner. user_id is nullable to preserve pre-auth rows
(existing prod-eval sessions have no user); new sessions created through
the authenticated API always populate it.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"])

    op.add_column(
        "sessions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_sessions_user",
        "sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])
    op.create_index(
        "ix_sessions_user_opened",
        "sessions",
        ["user_id", "opened_at"],
    )

    op.add_column(
        "sessions",
        sa.Column("title", sa.String(length=200), nullable=True),
    )

    # pgcrypto powers gen_random_uuid(); safe to CREATE IF NOT EXISTS.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")


def downgrade() -> None:
    op.drop_column("sessions", "title")
    op.drop_index("ix_sessions_user_opened", table_name="sessions")
    op.drop_index("ix_sessions_user_id", table_name="sessions")
    op.drop_constraint("fk_sessions_user", "sessions", type_="foreignkey")
    op.drop_column("sessions", "user_id")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
