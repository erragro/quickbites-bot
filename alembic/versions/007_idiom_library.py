"""idiom library: idiom_library + idiom_translations

Revision ID: 007
Revises: 006
Create Date: 2026-08-20

An English source phrase maps to per-language natural equivalents. The
Contract Reader translation pipeline scans Stage 3 English output for
these phrases via Aho-Corasick (constant-time regardless of library
size), swaps them with placeholder tokens before sending to Mayura,
then swaps them back with the pre-verified target-language equivalent.

This gives us DETERMINISTIC idiom translation — the equivalents are
hand-curated (or admin-added) rather than left to a general-purpose
translator that literalises "at the end of the day" into a phrase
about the actual last hour of a shift.

Two tables:
  idiom_library         The English source. One row per idiom, with a
                        meaning gloss and category. Category helps the
                        admin UI filter (legal/work/money/general) and
                        also lets the runtime skip low-relevance
                        categories if it wanted to (unused today).
  idiom_translations    Per-language natural equivalent. Composite
                        unique on (idiom_id, language).

Seed: ~25 idioms most relevant to gig-worker contracts and support
content, with Hindi + Bengali + Tamil equivalents. Equivalents are
modern-colloquial (matches Mayura's mode) — the register a worker
would actually use in speech, not textbook-formal.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LANGUAGES = ("en", "hi", "bn", "ta", "te", "kn", "mr")
_LANG_CHECK = "language IN (" + ", ".join(f"'{lang}'" for lang in LANGUAGES) + ")"

CATEGORIES = ("legal", "work", "money", "general", "safety")
_CAT_CHECK = "category IN (" + ", ".join(f"'{c}'" for c in CATEGORIES) + ")"


def upgrade() -> None:
    op.create_table(
        "idiom_library",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # The English source phrase. Matched case-insensitively at
        # runtime; store lowercased for consistency.
        sa.Column("source_phrase", sa.String(length=200), nullable=False),
        # Short English gloss so translators understand meaning before
        # writing an equivalent. e.g., "act with honesty and fairness".
        sa.Column("meaning", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=20), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
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
        sa.UniqueConstraint(
            "source_phrase", "tenant_id",
            name="uq_idiom_library_phrase_tenant",
        ),
        sa.CheckConstraint(_CAT_CHECK, name="ck_idiom_library_category"),
    )
    op.create_index(
        "ix_idiom_library_active", "idiom_library", ["is_active"],
    )
    op.create_index(
        "ix_idiom_library_tenant", "idiom_library", ["tenant_id"],
    )

    op.create_table(
        "idiom_translations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "idiom_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("idiom_library.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("language", sa.String(length=10), nullable=False),
        # The natural equivalent in the target language. Modern-
        # colloquial register: how a Bengali migrant worker would
        # actually say this to a friend.
        sa.Column("translation", sa.Text(), nullable=False),
        # Optional usage note ("prefer this in formal contracts") for
        # admins scanning the library.
        sa.Column("notes", sa.Text(), nullable=True),
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
        sa.UniqueConstraint(
            "idiom_id", "language",
            name="uq_idiom_translations_idiom_lang",
        ),
        sa.CheckConstraint(_LANG_CHECK, name="ck_idiom_translations_language"),
    )
    op.create_index(
        "ix_idiom_translations_lang_active",
        "idiom_translations",
        ["language", "is_active"],
    )

    _seed(op)


def _seed(op) -> None:
    """Seed ~25 contract- and support-relevant idioms with hi/bn/ta.

    Equivalents were hand-picked for modern-colloquial register — the
    voice a worker would actually use in speech. Where a natural
    idiom doesn't exist in the target language, we substitute the
    closest plain-language equivalent rather than force a literal
    translation.
    """
    # ---- source phrases ----
    op.execute(
        """
        INSERT INTO idiom_library (source_phrase, meaning, category) VALUES
        ('in good faith',          'Act with honesty and fair intent, not to deceive.', 'legal'),
        ('at your own risk',       'You bear responsibility if something goes wrong.', 'legal'),
        ('hold harmless',          'Protect the company from any legal claims or costs.', 'legal'),
        ('without prejudice',      'Statements made here cannot be used against you later.', 'legal'),
        ('for the avoidance of doubt', 'To be perfectly clear — just spelling this out.', 'legal'),
        ('time is of the essence', 'Deadlines are strict; delays break the agreement.', 'legal'),
        ('at the sole discretion of', 'The company decides alone, without needing your agreement.', 'legal'),
        ('subject to change',      'This can be modified later without asking you.', 'legal'),
        ('binding upon',           'This agreement legally applies to.', 'legal'),
        ('null and void',          'This becomes cancelled and has no effect.', 'legal'),
        ('at the end of the day',  'When everything is considered, the bottom line is.', 'general'),
        ('in the long run',        'Over time, considering the overall picture.', 'general'),
        ('on the flip side',       'On the other hand, looking at the opposite angle.', 'general'),
        ('come what may',          'Whatever happens, regardless of the outcome.', 'general'),
        ('bear in mind',           'Remember, keep this in your thoughts.', 'general'),
        ('make ends meet',         'Earn enough to cover basic living costs.', 'money'),
        ('break even',             'Cover your costs, no profit or loss.', 'money'),
        ('out of pocket',          'Money you paid yourself that should be reimbursed.', 'money'),
        ('cut corners',            'Skip steps to save time or money, often unsafely.', 'work'),
        ('go the extra mile',      'Do more than what is required.', 'work'),
        ('call in sick',           'Tell your employer you cannot work today because of illness.', 'work'),
        ('clock in',               'Start your work shift, mark yourself present.', 'work'),
        ('clock out',              'End your work shift, mark yourself off.', 'work'),
        ('under the table',        'Payment done secretly to avoid taxes or records.', 'money'),
        ('put in writing',         'Make it a written record so it can be proven later.', 'legal');
        """
    )

    # ---- Hindi (hi) equivalents ----
    # Modern-colloquial Hindi — the Hinglish register gig workers use
    # in WhatsApp and speech. Some phrases have no natural Hindi idiom
    # so we use plain language.
    op.execute(
        """
        WITH i AS (SELECT id, source_phrase FROM idiom_library)
        INSERT INTO idiom_translations (idiom_id, language, translation)
        SELECT i.id, 'hi', t.translation FROM (VALUES
        ('in good faith',                      'अच्छी नीयत से'),
        ('at your own risk',                   'अपनी ज़िम्मेदारी पर'),
        ('hold harmless',                      'ज़िम्मेदार नहीं मानेगा'),
        ('without prejudice',                  'बिना किसी नुकसान के'),
        ('for the avoidance of doubt',         'साफ़ बात यह है कि'),
        ('time is of the essence',             'time पर काम होना ज़रूरी है'),
        ('at the sole discretion of',          'की मर्ज़ी पर'),
        ('subject to change',                  'बदल भी सकता है'),
        ('binding upon',                       'पर लागू होगा'),
        ('null and void',                      'रद्द हो जाएगा'),
        ('at the end of the day',              'देखा जाए तो'),
        ('in the long run',                    'आगे चलकर'),
        ('on the flip side',                   'दूसरी तरफ़'),
        ('come what may',                      'चाहे कुछ भी हो'),
        ('bear in mind',                       'ध्यान रखिए कि'),
        ('make ends meet',                     'गुज़ारा चलाना'),
        ('break even',                         'बराबरी पर आना'),
        ('out of pocket',                      'अपनी जेब से'),
        ('cut corners',                        'shortcut मारना'),
        ('go the extra mile',                  'ज़्यादा मेहनत करना'),
        ('call in sick',                       'बीमारी की छुट्टी लेना'),
        ('clock in',                           'shift शुरू करना'),
        ('clock out',                          'shift खत्म करना'),
        ('under the table',                    'चुपके से पैसा देना'),
        ('put in writing',                     'लिखित में देना')
        ) AS t(source_phrase, translation)
        JOIN i ON i.source_phrase = t.source_phrase;
        """
    )

    # ---- Bengali (bn) equivalents ----
    op.execute(
        """
        WITH i AS (SELECT id, source_phrase FROM idiom_library)
        INSERT INTO idiom_translations (idiom_id, language, translation)
        SELECT i.id, 'bn', t.translation FROM (VALUES
        ('in good faith',                      'সৎ ভাবে'),
        ('at your own risk',                   'নিজের ঝুঁকিতে'),
        ('hold harmless',                      'দায়ী মনে করবে না'),
        ('without prejudice',                  'কোনো ক্ষতি ছাড়াই'),
        ('for the avoidance of doubt',         'পরিষ্কার করে বলছি'),
        ('time is of the essence',             'সময় মতো কাজ শেষ করা জরুরি'),
        ('at the sole discretion of',          'এর ইচ্ছার উপর'),
        ('subject to change',                  'পরিবর্তন হতে পারে'),
        ('binding upon',                       'এর উপর প্রযোজ্য'),
        ('null and void',                      'বাতিল হয়ে যাবে'),
        ('at the end of the day',              'সব মিলিয়ে দেখলে'),
        ('in the long run',                    'দীর্ঘমেয়াদে'),
        ('on the flip side',                   'অন্য দিকে'),
        ('come what may',                      'যাই হোক না কেন'),
        ('bear in mind',                       'মনে রাখবেন যে'),
        ('make ends meet',                     'সংসার চালানো'),
        ('break even',                         'খরচ পুষিয়ে নেওয়া'),
        ('out of pocket',                      'নিজের পকেট থেকে'),
        ('cut corners',                        'shortcut মারা'),
        ('go the extra mile',                  'বেশি পরিশ্রম করা'),
        ('call in sick',                       'অসুস্থতার ছুটি নেওয়া'),
        ('clock in',                           'shift শুরু করা'),
        ('clock out',                          'shift শেষ করা'),
        ('under the table',                    'গোপনে টাকা দেওয়া'),
        ('put in writing',                     'লিখিত ভাবে দেওয়া')
        ) AS t(source_phrase, translation)
        JOIN i ON i.source_phrase = t.source_phrase;
        """
    )

    # ---- Tamil (ta) equivalents ----
    op.execute(
        """
        WITH i AS (SELECT id, source_phrase FROM idiom_library)
        INSERT INTO idiom_translations (idiom_id, language, translation)
        SELECT i.id, 'ta', t.translation FROM (VALUES
        ('in good faith',                      'நல்ல எண்ணத்துடன்'),
        ('at your own risk',                   'உங்கள் சொந்த பொறுப்பில்'),
        ('hold harmless',                      'பொறுப்பாக்க மாட்டாது'),
        ('without prejudice',                  'எந்த சேதமும் இல்லாமல்'),
        ('for the avoidance of doubt',         'தெளிவாகச் சொல்ல வேண்டுமெனில்'),
        ('time is of the essence',             'நேரத்தில் முடிக்க வேண்டும்'),
        ('at the sole discretion of',          'இன் விருப்பப்படி'),
        ('subject to change',                  'மாற்றக்கூடும்'),
        ('binding upon',                       'மீது பொருந்தும்'),
        ('null and void',                      'செல்லாது ஆகும்'),
        ('at the end of the day',              'இறுதியில் பார்த்தால்'),
        ('in the long run',                    'நீண்ட காலத்தில்'),
        ('on the flip side',                   'மறுபுறம்'),
        ('come what may',                      'என்ன வந்தாலும்'),
        ('bear in mind',                       'நினைவில் கொள்ளுங்கள்'),
        ('make ends meet',                     'குடும்பம் நடத்துதல்'),
        ('break even',                         'செலவைச் சரிக்கட்டுதல்'),
        ('out of pocket',                      'சொந்த பணத்தில்'),
        ('cut corners',                        'shortcut எடுத்தல்'),
        ('go the extra mile',                  'கூடுதலாக உழைத்தல்'),
        ('call in sick',                       'உடம்பு சரியில்லை என்று leave எடுத்தல்'),
        ('clock in',                           'shift ஆரம்பித்தல்'),
        ('clock out',                          'shift முடித்தல்'),
        ('under the table',                    'ரகசியமாக பணம் கொடுத்தல்'),
        ('put in writing',                     'எழுத்து வடிவில் கொடுத்தல்')
        ) AS t(source_phrase, translation)
        JOIN i ON i.source_phrase = t.source_phrase;
        """
    )


def downgrade() -> None:
    op.drop_index(
        "ix_idiom_translations_lang_active", table_name="idiom_translations",
    )
    op.drop_table("idiom_translations")
    op.drop_index("ix_idiom_library_tenant", table_name="idiom_library")
    op.drop_index("ix_idiom_library_active", table_name="idiom_library")
    op.drop_table("idiom_library")
