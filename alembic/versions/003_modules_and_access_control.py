"""add modules registry + user_module_access + users.is_super_admin

Revision ID: 003
Revises: 002
Create Date: 2026-08-11

Turns the app from single-purpose (chatbot only) into a multi-module
platform with per-user access control.

Design:
- `modules`: registry row per feature module. Keyed by a stable `key`
  (e.g. "chatbot") that both backend routes and the frontend
  module-list can reference. `is_system=true` protects seeded rows
  from admin-panel deletion.
- `user_module_access`: composite-PK grant row. access_level is one of
  view/edit/admin so the frontend can degrade UIs per level; the
  ordering is view < edit < admin.
- `users.is_super_admin`: single flag for "can grant module access to
  others / manage users / seed modules". Kept separate from
  user_module_access so bootstrap doesn't need a self-referential
  chicken-and-egg for the very first admin.

Seed: inserts the 'chatbot' module here so the app is usable after
migration without another manual step.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "modules",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("key", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=50), nullable=True),
        sa.Column("path", sa.String(length=100), nullable=False),
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("key", name="uq_modules_key"),
    )

    op.create_table(
        "user_module_access",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "module_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("modules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("access_level", sa.String(length=20), nullable=False),
        sa.Column(
            "granted_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "granted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("user_id", "module_id", name="pk_user_module_access"),
        sa.CheckConstraint(
            "access_level IN ('view','edit','admin')",
            name="ck_user_module_access_level",
        ),
    )
    op.create_index(
        "ix_user_module_access_module",
        "user_module_access",
        ["module_id"],
    )

    op.add_column(
        "users",
        sa.Column(
            "is_super_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.create_index("ix_users_super_admin", "users", ["is_super_admin"])

    # Seed the chatbot module so the app is functional immediately after
    # migration. Keeping this as SQL (not a Python data-migration) so
    # rollback via `alembic downgrade -1` doesn't leave the row orphaned.
    op.execute(
        """
        INSERT INTO modules (key, name, description, icon, path, is_system, sort_order)
        VALUES (
            'chatbot',
            'Chatbot',
            'Multilingual customer-support conversation. Supports English, Hindi, and Indian language routing through Sarvam AI.',
            'MessageSquare',
            '/chat',
            true,
            10
        )
        """
    )


def downgrade() -> None:
    op.drop_index("ix_users_super_admin", table_name="users")
    op.drop_column("users", "is_super_admin")
    op.drop_index("ix_user_module_access_module", table_name="user_module_access")
    op.drop_table("user_module_access")
    op.drop_table("modules")
