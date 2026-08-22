"""uploaded_contracts: target_language + target_script

Revision ID: 006
Revises: 005
Create Date: 2026-08-15

The worker picks the output language on the upload form. Contract Reader
is for gig workers who often can't read English well, so the LLM output
(Stage 3 clause explanations, implications, actions) must be rendered in
the worker's chosen language regardless of the contract's original
language. That's the whole product.

Two columns:
  target_language   Required at upload time. BCP-47 short code — the
                    same seven-language whitelist as fact_cards and
                    complaint_templates. Persisted so a re-process
                    (from the retry button) uses the same choice
                    without re-prompting.
  target_script     Optional. 'native' (default) or 'roman'. Only
                    meaningful for non-English languages. Day 13 wires
                    this up to Sarvam's transliteration endpoint so a
                    worker who reads Hindi only in Latin letters can
                    pick 'roman' and get 'aap ek swatantra thekedaar
                    hain' instead of 'आप एक स्वतंत्र ठेकेदार हैं'.
                    Today it's stored but not applied.

Existing rows are backfilled with target_language = the detected OCR
language (fallback 'en'). That preserves current output for anything
processed before this migration ran.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LANGUAGES = ("en", "hi", "bn", "ta", "te", "kn", "mr")
_LANG_CHECK = "target_language IN (" + ", ".join(f"'{lang}'" for lang in LANGUAGES) + ")"

SCRIPTS = ("native", "roman")
_SCRIPT_CHECK = "target_script IN (" + ", ".join(f"'{s}'" for s in SCRIPTS) + ")"


def upgrade() -> None:
    # Add as nullable so we can backfill safely, then flip to NOT NULL.
    op.add_column(
        "uploaded_contracts",
        sa.Column("target_language", sa.String(length=10), nullable=True),
    )
    op.add_column(
        "uploaded_contracts",
        sa.Column(
            "target_script",
            sa.String(length=10),
            nullable=False,
            server_default=sa.text("'native'"),
        ),
    )

    # Backfill: fall back to detected language, then to 'en' if that's null.
    op.execute(
        """
        UPDATE uploaded_contracts
        SET target_language = COALESCE(language, 'en')
        WHERE target_language IS NULL;
        """
    )

    op.alter_column(
        "uploaded_contracts",
        "target_language",
        existing_type=sa.String(length=10),
        nullable=False,
    )

    op.create_check_constraint(
        "ck_uploaded_contracts_target_language",
        "uploaded_contracts",
        _LANG_CHECK,
    )
    op.create_check_constraint(
        "ck_uploaded_contracts_target_script",
        "uploaded_contracts",
        _SCRIPT_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_uploaded_contracts_target_script",
        "uploaded_contracts",
        type_="check",
    )
    op.drop_constraint(
        "ck_uploaded_contracts_target_language",
        "uploaded_contracts",
        type_="check",
    )
    op.drop_column("uploaded_contracts", "target_script")
    op.drop_column("uploaded_contracts", "target_language")
