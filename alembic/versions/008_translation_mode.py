"""uploaded_contracts: translation_mode

Revision ID: 008
Revises: 007
Create Date: 2026-08-20

Sarvam Mayura v1 supports four register/tone modes for its translation:

  formal              Polite standard tone. Preserves original meaning
                      strictly. Good for official / business text.
                      Default here — a Hindi-target contract should
                      arrive as actual Hindi, not Hinglish, unless the
                      worker specifically wants otherwise.

  modern-colloquial   Casual everyday spoken style. Retains some
                      English loanwords the way people actually talk
                      on WhatsApp. Was our first-cut default; moved
                      here to opt-in.

  classic-colloquial  Traditional everyday spoken style. Minimal
                      English mixing, slightly more literary.

  code-mixed          Heavy code-mixing. Retains most English words.
                      Closest to how young urban gig workers speak.

Sarvam's own docs (confirmed via the thought-translate project which
tested every mode) are the source of truth for the mode names. See
also frontend/src/pages/ContractReaderPage.tsx where these become the
user-facing labels.

Stored on the contract row so a re-process from the retry button
uses the same choice without re-prompting.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MODES = ("formal", "modern-colloquial", "classic-colloquial", "code-mixed")
_MODE_CHECK = "translation_mode IN (" + ", ".join(f"'{m}'" for m in MODES) + ")"


def upgrade() -> None:
    op.add_column(
        "uploaded_contracts",
        sa.Column(
            "translation_mode",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'formal'"),
        ),
    )
    op.create_check_constraint(
        "ck_uploaded_contracts_translation_mode",
        "uploaded_contracts",
        _MODE_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_uploaded_contracts_translation_mode",
        "uploaded_contracts",
        type_="check",
    )
    op.drop_column("uploaded_contracts", "translation_mode")
