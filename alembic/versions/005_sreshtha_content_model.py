"""sreshtha content model: fact_cards, schemes, scheme_translations,
complaint_templates, uploaded_contracts + module reseed

Revision ID: 005
Revises: 004
Create Date: 2026-08-14

Content substrate for the five Sreshtha modules:

- fact_cards               Rights Guide. One row per (topic_key, language).
                           Each carries a summary, citation, action steps,
                           and an optional pre-generated audio URL (TTS).
- schemes                  Government scheme metadata + structured
                           eligibility rules (JSONB). One row per scheme,
                           language-agnostic.
- scheme_translations      Language-scoped copy for schemes. Separate table
                           so the eligibility rules stay canonical and the
                           Schemes Finder doesn't need to join across
                           translated rows to match by state/occupation.
- complaint_templates      Complaint Helper drafts. One row per
                           (topic_key, language). Body has {{variable}}
                           placeholders + a routing JSON for the escalation
                           ladder (Labour Commissioner, e-Shram, POSH,
                           ombudsman, Labourline).
- uploaded_contracts       Contract Reader uploads. Tracks the file plus
                           the three-stage processing state
                           (understand → research → synthesise).

Also reseeds the `modules` table with the four new Sreshtha modules
(contract_reader, rights_guide, schemes_finder, complaint_helper) and
retargets the existing chatbot module's description. Existing
UserModuleAccess grants against chatbot are preserved.

Scaffolding data: 3 fact cards, 3 schemes, 3 complaint templates in EN.
Full content lands Day 9-10 (fact cards) + Day 14 (schemes) + Day 15
(complaint templates).

Deferred to Day 11: pgvector extension + `embeddings` table (RAG index
over fact cards + contract clauses). Doing it here would force a
docker-image swap; better to bundle with the migration that actually
uses it.

Multi-tenancy is future-proofed with nullable `tenant_id` FKs on every
content row. NULL means "shared across all tenants" — v1 default.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- Constants -------------------------------------------------------------

# BCP-47 language subtags we accept in v1. Enforced by the CHECK constraint
# below rather than a Postgres enum — cheaper to add new languages later.
LANGUAGES = ("en", "hi", "bn", "ta", "te", "kn", "mr")
_LANG_CHECK = "language IN (" + ", ".join(f"'{lang}'" for lang in LANGUAGES) + ")"

# Uploaded-contract lifecycle. Every row enters as 'uploaded'; the
# processor advances it through the stages, terminating at 'ready' or
# 'failed'.
CONTRACT_STATUSES = (
    "uploaded",       # file stored, no processing started
    "ocr_pending",    # queued for OCR
    "ocr_done",       # OCR text extracted
    "processing",     # three-stage LLM pipeline running
    "ready",          # all three stages complete
    "failed",         # unrecoverable error; see error_message
)
_STATUS_CHECK = "status IN (" + ", ".join(f"'{s}'" for s in CONTRACT_STATUSES) + ")"


def upgrade() -> None:
    # ---------------- fact_cards ----------------
    op.create_table(
        "fact_cards",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # topic_key groups all language variants of the same fact. e.g.
        # ('minimum_wage', 'hi') and ('minimum_wage', 'bn') are two rows
        # sharing topic_key='minimum_wage'.
        sa.Column("topic_key", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        # 2-4 short paragraphs, plain-language. Rendered as-is (no markdown
        # parsing in the demo UI; TTS reads the raw text).
        sa.Column("summary", sa.Text(), nullable=False),
        # Statute / scheme / policy citation. Includes URL when available.
        # Kept as free text so we can cite non-URL things (Act name +
        # section number) without forcing a schema break.
        sa.Column("citation", sa.Text(), nullable=True),
        # Array of {label, description, url?}. Rendered as a numbered list
        # under "What to do about it".
        sa.Column("action_steps", postgresql.JSONB(), nullable=True),
        sa.Column("icon", sa.String(length=50), nullable=True),
        # Pre-generated Sarvam TTS URL, populated by a background job when
        # the card is created/updated. Null means "generate on demand".
        sa.Column("audio_url", sa.String(length=500), nullable=True),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        # Multi-tenancy: NULL means shared. Populated per-tenant in v2 when
        # unions / welfare boards license the platform and want their own
        # curated overrides.
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
        sa.CheckConstraint(_LANG_CHECK, name="ck_fact_cards_language"),
        sa.UniqueConstraint(
            "topic_key", "language", "tenant_id",
            name="uq_fact_cards_topic_lang_tenant",
        ),
    )
    op.create_index(
        "ix_fact_cards_lang_active", "fact_cards", ["language", "is_active"],
    )
    op.create_index("ix_fact_cards_topic", "fact_cards", ["topic_key"])
    op.create_index("ix_fact_cards_tenant", "fact_cards", ["tenant_id"])

    # ---------------- schemes ----------------
    op.create_table(
        "schemes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("key", sa.String(length=80), nullable=False),
        # 'central', 'karnataka', 'rajasthan', 'tamil_nadu', ..., or 'all'
        # for schemes with no state filter. Nullable so an admin can
        # register a scheme before deciding its scope.
        sa.Column("state_scope", sa.String(length=40), nullable=True),
        # Structured eligibility. Shape:
        # {
        #   "occupations": ["delivery", "cab", "domestic", "any"],
        #   "min_age": 18,
        #   "max_age": 60,
        #   "states": ["karnataka", "rajasthan"] | null,
        #   "gender": "any" | "female" | "male",
        #   "requires_eshram": true,
        #   "requires_children": false
        # }
        # Missing keys mean "no filter". Schemes Finder passes the user's
        # profile through a match function; kept as JSONB so admins can
        # edit rules in v2 without a schema change.
        sa.Column(
            "eligibility_rules",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("apply_url", sa.String(length=500), nullable=True),
        # Array of {name, note?}. e.g. [{"name": "Aadhaar"}, {"name":
        # "Bank passbook", "note": "for direct benefit transfer"}].
        sa.Column(
            "docs_needed",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # Estimated time to complete the application. Free-form string so
        # admin can write "10 mins if you have Aadhaar" rather than being
        # boxed into minutes.
        sa.Column("estimated_time", sa.String(length=100), nullable=True),
        sa.Column("icon", sa.String(length=50), nullable=True),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
        ),
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
            "key", "tenant_id", name="uq_schemes_key_tenant",
        ),
    )
    op.create_index("ix_schemes_state_active", "schemes", ["state_scope", "is_active"])
    op.create_index("ix_schemes_tenant", "schemes", ["tenant_id"])

    # ---------------- scheme_translations ----------------
    # Separate table so eligibility rules stay canonical (unlike
    # fact_cards where the whole card is language-scoped). A scheme has
    # one metadata row and N translation rows.
    op.create_table(
        "scheme_translations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "scheme_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("schemes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        # Optional in-language note about how to apply — sits above the
        # apply_url link on the module UI.
        sa.Column("apply_note", sa.Text(), nullable=True),
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
        sa.CheckConstraint(_LANG_CHECK, name="ck_scheme_translations_language"),
        sa.UniqueConstraint(
            "scheme_id", "language", name="uq_scheme_translations_scheme_lang",
        ),
    )
    op.create_index(
        "ix_scheme_translations_lang", "scheme_translations", ["language"],
    )

    # ---------------- complaint_templates ----------------
    op.create_table(
        "complaint_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # 'wage_theft' | 'injury' | 'dismissal' | 'harassment' |
        # 'insurance' | 'other'. Kept as a free string so admins can
        # register topics without a migration.
        sa.Column("topic_key", sa.String(length=80), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        # Complaint body with {{variable}} placeholders. Rendered with the
        # existing Handlebars-style renderer used by ack templates. English
        # copy of the same complaint always accompanies the language
        # version — many portals demand English filings even from
        # non-English speakers.
        sa.Column("body", sa.Text(), nullable=False),
        # Escalation ladder. Shape:
        # [
        #   {"authority": "State Labour Commissioner",
        #    "contact": "0812-xxx-xxxx",
        #    "url": "...",
        #    "note": "File within 30 days"},
        #   {"authority": "India Labourline",
        #    "contact": "1800-419-1550"}
        # ]
        # UI renders as a "next steps" list.
        sa.Column(
            "routing",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # What the worker needs to fill in for this template. Array of
        # {key, label, type ('text'|'date'|'money'|'select'), help?,
        # options?}. Complaint Helper renders these as form fields.
        sa.Column(
            "required_fields",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
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
        sa.CheckConstraint(_LANG_CHECK, name="ck_complaint_templates_language"),
        sa.UniqueConstraint(
            "topic_key", "language", "tenant_id",
            name="uq_complaint_templates_topic_lang_tenant",
        ),
    )
    op.create_index(
        "ix_complaint_templates_lang_active",
        "complaint_templates",
        ["language", "is_active"],
    )
    op.create_index(
        "ix_complaint_templates_topic", "complaint_templates", ["topic_key"],
    )

    # ---------------- uploaded_contracts ----------------
    op.create_table(
        "uploaded_contracts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        # Object storage key. Local dev writes to a mounted directory;
        # Cloud Run reads/writes GCS. Format: 'contracts/{user_id}/{uuid}.pdf'.
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'uploaded'"),
        ),
        # Raw OCR text — kept for debugging, re-processing, and full-text
        # search over the corpus later. Nullable until OCR runs.
        sa.Column("ocr_text", sa.Text(), nullable=True),
        # Three-stage LLM pipeline output. Shape:
        # {
        #   "stage_1": {"clauses": [{"id", "text", "type"}], "contract_type": "aggregator"},
        #   "stage_2": {"annotations": [{"clause_id", "statute", "risk": "red|amber|green"}]},
        #   "stage_3": {"rendered": [{"clause_id", "original", "explanation", "risk", "action"}]}
        # }
        # Kept as JSONB so shape can evolve without migrations while we're
        # still iterating on prompts.
        sa.Column("stages", postgresql.JSONB(), nullable=True),
        # Detected language of the contract (may differ from the user's UI
        # language — the worker's contract is often English while their
        # UI is Bengali).
        sa.Column("language", sa.String(length=10), nullable=True),
        sa.Column("contract_type", sa.String(length=50), nullable=True),
        # Populated only on status='failed'. Human-readable so the user
        # sees "we couldn't read this file — try a clearer photo" not a
        # stack trace.
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.CheckConstraint(_STATUS_CHECK, name="ck_uploaded_contracts_status"),
    )
    op.create_index(
        "ix_uploaded_contracts_user_created",
        "uploaded_contracts",
        ["user_id", "created_at"],
    )
    op.create_index("ix_uploaded_contracts_status", "uploaded_contracts", ["status"])

    # ---------------- Module reseed + seed data ----------------
    _reseed_modules(op)
    _seed_scaffolding(op)


def _reseed_modules(op) -> None:
    """Add the four new Sreshtha modules and retarget the existing chatbot
    module's description. Existing UserModuleAccess grants on chatbot are
    preserved because we UPDATE, not DELETE+INSERT."""
    op.execute(
        """
        UPDATE modules
        SET name        = 'Chatbot Sahaayak',
            description = 'Ask about your rights, contracts, and schemes in your language. Every answer cites where it came from.',
            icon        = 'MessageSquare',
            sort_order  = 30
        WHERE key = 'chatbot';
        """
    )
    op.execute(
        """
        INSERT INTO modules (key, name, description, icon, path, is_system, sort_order) VALUES
          ('contract_reader',
           'Contract Reader',
           'Upload the contract you signed and see it explained clause by clause, in your language.',
           'FileText',
           '/contracts',
           true,
           10),
          ('rights_guide',
           'Rights Guide',
           'Curated fact cards on wages, safety, insurance, dismissal, and how to escalate. Cited from statute.',
           'ShieldCheck',
           '/rights',
           true,
           20),
          ('schemes_finder',
           'Schemes Finder',
           'Answer three questions and see every government scheme you''re already entitled to.',
           'Award',
           '/schemes',
           true,
           40),
          ('complaint_helper',
           'Complaint Helper',
           'Draft a complaint in your language, routed to the right authority. India Labourline is one tap away.',
           'FileWarning',
           '/complaint',
           true,
           50);
        """
    )


def _seed_scaffolding(op) -> None:
    """3 fact cards + 3 schemes + 3 complaint templates in EN.
    Enough scaffolding to test the CRUD paths without waiting for the
    full content curation on days 9-15."""

    # -------- fact_cards (3 EN scaffolding rows) --------
    op.execute(
        """
        INSERT INTO fact_cards
          (topic_key, language, title, summary, citation, action_steps, icon, sort_order)
        VALUES
        (
          'minimum_wage',
          'en',
          'Minimum wage for gig workers',
          'Central + state minimum wage laws apply to unorganised workers, but gig platforms have long argued their workers are "partners", not employees. The Code on Social Security 2020 changed that framing: platform-based workers are now a recognised category and are covered by welfare schemes, though the classic Minimum Wages Act still does not apply directly. State welfare boards (Karnataka, Rajasthan) are the practical route to floor-price protection today.',
          'Code on Social Security 2020, Sections 113-114. Karnataka Platform-Based Gig Workers (Social Security and Welfare) Ordinance, 2025.',
          '[
            {"label": "Register on e-Shram", "description": "This gets you a UAN and access to central welfare schemes.", "url": "https://eshram.gov.in"},
            {"label": "Check your state welfare board", "description": "Karnataka + Rajasthan have gig-worker-specific boards. Other states are following."},
            {"label": "Call India Labourline", "description": "For a formal complaint about wage theft or below-agreement pay.", "url": "tel:1800-419-1550"}
          ]'::jsonb,
          'IndianRupee',
          10
        ),
        (
          'injury_on_the_job',
          'en',
          'What happens if you''re injured while working',
          'Aggregator platforms under the Code on Social Security 2020 are responsible for contributing to a Social Security Fund that covers medical care and disability benefits for platform workers. Practically, most platforms also offer accident insurance up to a stated limit (varies by platform). The two claim paths run in parallel: your platform''s insurance and the state welfare board scheme (in Karnataka + Rajasthan).',
          'Code on Social Security 2020, Section 114. Central Motor Vehicles Rules amendment 2024 for aggregator responsibility.',
          '[
            {"label": "Report to platform immediately", "description": "Most platforms require a report within 24 hours to trigger insurance."},
            {"label": "Get medical documentation", "description": "Hospital receipts + doctor''s notes are essential for both platform and state claims."},
            {"label": "File a state welfare board claim (KA/RJ)", "description": "Separate from platform insurance; both can pay."},
            {"label": "Use Complaint Helper if the claim is denied", "description": "We''ll draft the escalation to the ombudsman for you."}
          ]'::jsonb,
          'HeartPulse',
          20
        ),
        (
          'grievance_escalation',
          'en',
          'How to escalate a complaint that''s going nowhere',
          'Platform customer support is the first door, but it''s designed for consumers, not workers. If the platform''s worker-support channel gives you nothing, the escalation ladder is: state Labour Commissioner (they can order the platform to respond) → India Labourline (they route to the right authority) → labour court or consumer court (for wage / contract disputes). All three accept complaints from workers directly, without a lawyer.',
          'Industrial Disputes Act 1947, Section 2A (individual disputes). Consumer Protection Act 2019. India Labourline (Ministry of Labour helpline).',
          '[
            {"label": "Call India Labourline first", "description": "1800-419-1550. They route your complaint to the right authority.", "url": "tel:1800-419-1550"},
            {"label": "File with your state Labour Commissioner", "description": "Every state has an office. They can summon the platform to respond."},
            {"label": "Use Complaint Helper", "description": "We draft the formal complaint for you in your language + English."}
          ]'::jsonb,
          'AlertTriangle',
          30
        );
        """
    )

    # -------- schemes (3 EN scaffolding rows) --------
    op.execute(
        """
        INSERT INTO schemes
          (key, state_scope, eligibility_rules, apply_url, docs_needed, estimated_time, icon, sort_order)
        VALUES
        (
          'e_shram',
          'all',
          '{
            "occupations": ["any"],
            "min_age": 16,
            "max_age": 59,
            "requires_eshram": false
          }'::jsonb,
          'https://eshram.gov.in',
          '[
            {"name": "Aadhaar"},
            {"name": "Aadhaar-linked mobile number"},
            {"name": "Bank account passbook", "note": "for benefit transfer"}
          ]'::jsonb,
          '10 minutes with Aadhaar',
          'IdCard',
          10
        ),
        (
          'pm_suraksha_bima_yojana',
          'all',
          '{
            "occupations": ["any"],
            "min_age": 18,
            "max_age": 70,
            "requires_bank_account": true
          }'::jsonb,
          'https://www.jansuraksha.gov.in/Forms-PMSBY.aspx',
          '[
            {"name": "Aadhaar"},
            {"name": "Bank account", "note": "PMSBY is a bank-linked scheme"}
          ]'::jsonb,
          '5 minutes at your bank',
          'ShieldPlus',
          20
        ),
        (
          'karnataka_platform_welfare',
          'karnataka',
          '{
            "occupations": ["delivery", "cab", "any"],
            "min_age": 18,
            "states": ["karnataka"],
            "requires_eshram": true
          }'::jsonb,
          'https://labour.karnataka.gov.in',
          '[
            {"name": "e-Shram UAN"},
            {"name": "Aadhaar"},
            {"name": "Platform employment proof", "note": "screenshot from the app is enough"}
          ]'::jsonb,
          '15 minutes online',
          'Landmark',
          30
        );
        """
    )

    # -------- scheme_translations (3 EN rows, one per scheme) --------
    op.execute(
        """
        WITH s AS (SELECT id, key FROM schemes)
        INSERT INTO scheme_translations (scheme_id, language, name, description, apply_note)
        SELECT s.id, t.language, t.name, t.description, t.apply_note FROM (VALUES
          ('e_shram', 'en',
           'e-Shram Registration',
           'Central government registry for all unorganised workers. Gets you a Universal Account Number (UAN) that unlocks eligibility for other welfare schemes and, in some states, direct benefit transfers. Free to register.',
           'Registration is free. Never pay anyone claiming to help you register.'),
          ('pm_suraksha_bima_yojana', 'en',
           'PM Suraksha Bima Yojana',
           'Government-backed accident insurance for anyone with a bank account. Rs 2 lakh cover for accidental death or permanent disability, Rs 1 lakh for partial disability. Premium is Rs 20 per year, auto-debited from your bank account.',
           'Enrol through your bank, either in-branch or via your bank''s app.'),
          ('karnataka_platform_welfare', 'en',
           'Karnataka Platform Gig Workers Welfare Fund',
           'State-level welfare fund funded by a 1-2 percent cess on platform transactions in Karnataka. Provides health cover, accident insurance, and skilling grants for gig workers. Requires e-Shram registration first.',
           'Register once your e-Shram UAN is issued. State board processes take 2-3 weeks.')
        ) AS t(scheme_key, language, name, description, apply_note)
        JOIN s ON s.key = t.scheme_key;
        """
    )

    # -------- complaint_templates (3 EN rows) --------
    op.execute(
        """
        INSERT INTO complaint_templates
          (topic_key, language, title, body, routing, required_fields)
        VALUES
        (
          'wage_theft',
          'en',
          'Wage theft complaint (unpaid or under-paid work)',
          E'To: {{routing.primary.authority}}\n\nSubject: Complaint regarding unpaid wages for gig work\n\nI am a {{fields.occupation}} working on the {{fields.platform}} platform in {{fields.city}}. My worker ID / partner ID is {{fields.worker_id}}.\n\nOn {{fields.incident_date}}, I performed work for which I was to be paid Rs {{fields.expected_amount}}. The actual amount received was Rs {{fields.actual_amount}}. The reason given by the platform, if any, was: {{fields.platform_reason}}.\n\nI attempted to resolve this through the platform''s in-app support on {{fields.support_contact_date}} but received no adequate response.\n\nI request your office to take up this matter under the applicable labour welfare provisions.\n\nSincerely,\n{{fields.name}}\n{{fields.phone}}\n{{fields.address}}',
          '[
            {"authority": "State Labour Commissioner", "note": "Primary channel; can summon the platform", "url": null},
            {"authority": "India Labourline", "contact": "1800-419-1550", "url": null, "note": "National helpline; will route to your state"},
            {"authority": "Consumer Court", "note": "Alternate channel for disputes over the transaction itself", "url": null}
          ]'::jsonb,
          '[
            {"key": "name", "label": "Your full name", "type": "text"},
            {"key": "phone", "label": "Your phone number", "type": "text"},
            {"key": "address", "label": "Your address", "type": "text"},
            {"key": "city", "label": "City where you work", "type": "text"},
            {"key": "occupation", "label": "Type of work", "type": "select", "options": ["delivery rider", "cab driver", "auto driver", "domestic worker", "other"]},
            {"key": "platform", "label": "Platform name", "type": "text", "help": "e.g. Swiggy, Uber, Urban Company"},
            {"key": "worker_id", "label": "Your worker/partner ID on the platform", "type": "text"},
            {"key": "incident_date", "label": "Date of the disputed work", "type": "date"},
            {"key": "expected_amount", "label": "Amount you were supposed to receive (Rs)", "type": "money"},
            {"key": "actual_amount", "label": "Amount actually received (Rs)", "type": "money"},
            {"key": "platform_reason", "label": "Reason the platform gave, if any", "type": "text"},
            {"key": "support_contact_date", "label": "Date you contacted platform support", "type": "date"}
          ]'::jsonb
        ),
        (
          'injury',
          'en',
          'Injury compensation claim (injured while working)',
          E'To: {{routing.primary.authority}}\n\nSubject: Claim for compensation following injury sustained during platform work\n\nI, {{fields.name}}, am a {{fields.occupation}} working through the {{fields.platform}} platform. My worker ID is {{fields.worker_id}}. My e-Shram UAN, if registered, is {{fields.eshram_uan}}.\n\nOn {{fields.incident_date}} at approximately {{fields.incident_time}}, I sustained an injury while performing work assigned through the platform. The nature of the injury is: {{fields.injury_description}}.\n\nMedical treatment was received at {{fields.hospital_name}}, with total costs of Rs {{fields.medical_costs}} incurred so far. I have been unable to work for {{fields.days_off}} days as a result.\n\nI request your office to process my claim under the Code on Social Security 2020 provisions for platform workers.\n\nSincerely,\n{{fields.name}}\n{{fields.phone}}',
          '[
            {"authority": "State Welfare Board (if in KA or RJ)", "note": "Primary route for state-level cover"},
            {"authority": "Platform CX with claim escalation", "note": "Insurance cover on most platforms"},
            {"authority": "ESIC if applicable", "note": "For platforms that participate in ESIC"},
            {"authority": "India Labourline", "contact": "1800-419-1550"}
          ]'::jsonb,
          '[
            {"key": "name", "label": "Your full name", "type": "text"},
            {"key": "phone", "label": "Your phone number", "type": "text"},
            {"key": "occupation", "label": "Type of work", "type": "select", "options": ["delivery rider", "cab driver", "auto driver", "domestic worker", "other"]},
            {"key": "platform", "label": "Platform name", "type": "text"},
            {"key": "worker_id", "label": "Your worker/partner ID", "type": "text"},
            {"key": "eshram_uan", "label": "e-Shram UAN (if you have one)", "type": "text", "help": "12-digit number from your e-Shram card"},
            {"key": "incident_date", "label": "Date of injury", "type": "date"},
            {"key": "incident_time", "label": "Approximate time", "type": "text"},
            {"key": "injury_description", "label": "What happened and what part of the body was injured", "type": "text"},
            {"key": "hospital_name", "label": "Hospital or clinic where treated", "type": "text"},
            {"key": "medical_costs", "label": "Medical costs so far (Rs)", "type": "money"},
            {"key": "days_off", "label": "Days unable to work", "type": "text"}
          ]'::jsonb
        ),
        (
          'harassment',
          'en',
          'Workplace harassment complaint',
          E'To: {{routing.primary.authority}}\n\nSubject: Complaint of workplace harassment\n\nI, {{fields.name}}, am a {{fields.occupation}} working through the {{fields.platform}} platform in {{fields.city}}. My worker ID is {{fields.worker_id}}.\n\nOn {{fields.incident_date}}, I experienced the following: {{fields.incident_description}}.\n\nThe person or people involved were: {{fields.perpetrator_description}}.\n\nAny witnesses or evidence I have: {{fields.evidence}}.\n\nI request your office to take this complaint under the appropriate provisions of the POSH Act, 2013 and applicable labour law.\n\nSincerely,\n{{fields.name}}\n{{fields.phone}}',
          '[
            {"authority": "Internal Complaints Committee (POSH Act 2013)", "note": "Every platform above threshold is required to have one"},
            {"authority": "Local Committee at District Officer", "note": "For platforms without an ICC or if you cannot use the ICC"},
            {"authority": "Local Police Station", "note": "For criminal-level incidents; do not delay"},
            {"authority": "India Labourline", "contact": "1800-419-1550"}
          ]'::jsonb,
          '[
            {"key": "name", "label": "Your full name", "type": "text"},
            {"key": "phone", "label": "Your phone number", "type": "text"},
            {"key": "city", "label": "City", "type": "text"},
            {"key": "occupation", "label": "Type of work", "type": "select", "options": ["delivery rider", "cab driver", "auto driver", "domestic worker", "other"]},
            {"key": "platform", "label": "Platform name", "type": "text"},
            {"key": "worker_id", "label": "Your worker/partner ID", "type": "text"},
            {"key": "incident_date", "label": "Date of incident", "type": "date"},
            {"key": "incident_description", "label": "What happened", "type": "text"},
            {"key": "perpetrator_description", "label": "Who was involved (describe, do not need to name)", "type": "text"},
            {"key": "evidence", "label": "Any witnesses or evidence", "type": "text"}
          ]'::jsonb
        );
        """
    )


def downgrade() -> None:
    # Reverse module reseed. Deleting the 4 new modules cascades any
    # UserModuleAccess grants against them (they're cascade-delete FKs).
    # The chatbot description update is NOT reverted — the old QuickBites
    # copy is gone.
    op.execute(
        "DELETE FROM modules WHERE key IN "
        "('contract_reader', 'rights_guide', 'schemes_finder', 'complaint_helper');"
    )

    op.drop_index(
        "ix_uploaded_contracts_status", table_name="uploaded_contracts",
    )
    op.drop_index(
        "ix_uploaded_contracts_user_created", table_name="uploaded_contracts",
    )
    op.drop_table("uploaded_contracts")

    op.drop_index(
        "ix_complaint_templates_topic", table_name="complaint_templates",
    )
    op.drop_index(
        "ix_complaint_templates_lang_active", table_name="complaint_templates",
    )
    op.drop_table("complaint_templates")

    op.drop_index("ix_scheme_translations_lang", table_name="scheme_translations")
    op.drop_table("scheme_translations")

    op.drop_index("ix_schemes_tenant", table_name="schemes")
    op.drop_index("ix_schemes_state_active", table_name="schemes")
    op.drop_table("schemes")

    op.drop_index("ix_fact_cards_tenant", table_name="fact_cards")
    op.drop_index("ix_fact_cards_topic", table_name="fact_cards")
    op.drop_index("ix_fact_cards_lang_active", table_name="fact_cards")
    op.drop_table("fact_cards")
