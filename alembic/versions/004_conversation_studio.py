"""conversation studio: business_units, issue_types, data_point_registry,
issue_type_data_points, acknowledgment_templates, intent_detection_cases

Revision ID: 004
Revises: 003
Create Date: 2026-08-12

Turns the chatbot from free-text-first to chip-tap-first. Adds the config
schema that a no-code admin panel can drive:

- business_units       Hierarchical tree (Order issues → Delivery → ...).
- issue_types          Leaf nodes the customer taps. Each carries the
                       intent it routes to (so Stage 2's matrix stays
                       untouched) and its own data-point contract.
- data_point_registry  Registry of Python fetchers exposed to the admin
                       panel by key. Admin can't add fetchers (those are
                       code), but can pick which existing ones an issue
                       type consumes — no arbitrary code execution.
- issue_type_data_points   many-to-many. Ordered so the enricher runs
                           requireds first, best-effort ones second.
- acknowledgment_templates Multiple weighted variants per issue type so
                           the ack line varies across sessions. Variable
                           substitution is Handlebars-style {{path.to.field}}
                           against the enriched context blob.
- intent_detection_cases   Free-text messages + the intent the LLM
                           picked; grows into the training set for a
                           distilled deterministic classifier later.

Sessions gets two nullable columns (issue_type_id, business_unit_id)
so subsequent turns know which issue is active.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------- business_units ----------------
    op.create_table(
        "business_units",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_units.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
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
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("code", name="uq_business_units_code"),
    )
    op.create_index("ix_business_units_parent", "business_units", ["parent_id"])

    # ---------------- data_point_registry ----------------
    op.create_table(
        "data_point_registry",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        # `fetcher_ref` is a stable string the runtime maps to a Python
        # callable. Admin panel can't add new refs; the mapping lives in
        # app/conversation_studio/service.py.
        sa.Column("fetcher_ref", sa.String(length=150), nullable=False),
        sa.Column(
            "is_system",
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
        sa.UniqueConstraint("key", name="uq_data_point_registry_key"),
    )

    # ---------------- issue_types ----------------
    op.create_table(
        "issue_types",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "business_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_units.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=50), nullable=True),
        # routes_to_intent binds this admin-facing issue type back to the
        # existing 13-intent taxonomy Stage 2's matrix already reasons
        # about. Nullable so an admin can register experimental issue
        # types before wiring them into the matrix.
        sa.Column("routes_to_intent", sa.String(length=50), nullable=True),
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
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "business_unit_id", "code", name="uq_issue_types_bu_code",
        ),
    )
    op.create_index("ix_issue_types_bu", "issue_types", ["business_unit_id"])
    op.create_index(
        "ix_issue_types_routed_intent", "issue_types", ["routes_to_intent"],
    )

    # ---------------- issue_type_data_points (M:N) ----------------
    op.create_table(
        "issue_type_data_points",
        sa.Column(
            "issue_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("issue_types.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "data_point_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_point_registry.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "is_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
        ),
        sa.PrimaryKeyConstraint(
            "issue_type_id", "data_point_id", name="pk_issue_type_data_points",
        ),
    )

    # ---------------- acknowledgment_templates ----------------
    op.create_table(
        "acknowledgment_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "issue_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("issue_types.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column(
            "weight",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
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
    )
    op.create_index(
        "ix_ack_templates_issue_type",
        "acknowledgment_templates",
        ["issue_type_id", "is_active"],
    )

    # ---------------- intent_detection_cases ----------------
    op.create_table(
        "intent_detection_cases",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("customer_message", sa.Text(), nullable=False),
        sa.Column(
            "matched_issue_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("issue_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # "rule" | "llm" | "human_verified"
        sa.Column("matched_by", sa.String(length=20), nullable=False),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column(
            "seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "seen_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.create_index(
        "ix_intent_cases_lookup",
        "intent_detection_cases",
        ["matched_issue_type_id", "matched_by"],
    )

    # ---------------- sessions: issue_type_id + business_unit_id ----------------
    op.add_column(
        "sessions",
        sa.Column(
            "issue_type_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("issue_types.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "sessions",
        sa.Column(
            "business_unit_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_units.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_sessions_issue_type", "sessions", ["issue_type_id"])

    # ---------------- Seed data ----------------
    _seed(op)


def _seed(op) -> None:
    """Starter dataset: 4 BUs, 11 issue types, 33 templates, 7 data points.

    All rows carry `is_system=true` so admin-panel deletes leave them
    alone. Deliberate: these back the existing Stage 2 matrix and
    deleting them would silently break the chatbot.
    """
    # -------- data_point_registry --------
    op.execute(
        """
        INSERT INTO data_point_registry (key, name, description, fetcher_ref, is_system) VALUES
        ('customer_profile',
         'Customer profile + abuse signals',
         'Loyalty tier, wallet balance, complaint/rejection rates, refund totals.',
         'repository.fetch_customer_full',
         true),
        ('order_full',
         'Order + items',
         'Full order row with joined line items.',
         'repository.fetch_order_full',
         true),
        ('rider_history',
         'Rider history',
         'Rider profile + verified/unverified incident counts, incident types seen.',
         'repository.fetch_rider_full',
         true),
        ('restaurant_history',
         'Restaurant history',
         'Restaurant rating, review count, recent complaint volume.',
         'repository.fetch_restaurant_full',
         true),
        ('customer_complaints',
         'Recent complaints',
         'Last 10 complaints filed by this customer, with status + resolution.',
         'repository.fetch_customer_complaints',
         true),
        ('customer_refunds_30d',
         'Refunds in last 30 days',
         'Refund count + total INR issued to this customer over last 30 days.',
         'repository.fetch_customer_refunds',
         true),
        ('rider_incidents_for_order',
         'Rider incidents on this order',
         'Any rider incidents logged specifically against this order.',
         'repository.fetch_rider_incidents_for_order',
         true);
        """
    )

    # -------- business_units --------
    op.execute(
        """
        INSERT INTO business_units (code, name, icon, sort_order) VALUES
        ('orders',    'Order issues',        'UtensilsCrossed', 10),
        ('delivery',  'Delivery problems',   'Truck',           20),
        ('payments',  'Payments & refunds',  'CreditCard',      30),
        ('account',   'Account & other',     'HelpCircle',      40);
        """
    )

    # -------- issue_types --------
    # (business_unit lookup by code + intent binding to the matrix taxonomy)
    op.execute(
        """
        WITH bu AS (SELECT id, code FROM business_units)
        INSERT INTO issue_types
            (business_unit_id, code, name, description, icon, routes_to_intent, sort_order)
        VALUES
          ((SELECT id FROM bu WHERE code='orders'),
           'missing_item', 'Missing item',
           'One or more items from my order were not delivered.',
           'PackageX', 'missing_item', 10),
          ((SELECT id FROM bu WHERE code='orders'),
           'wrong_order', 'Wrong order',
           'I received an order that wasn''t what I ordered.',
           'PackageSearch', 'wrong_order', 20),
          ((SELECT id FROM bu WHERE code='orders'),
           'cold_food', 'Food arrived cold',
           'The food was cold or looked like it had been sitting.',
           'Snowflake', 'cold_food', 30),

          ((SELECT id FROM bu WHERE code='delivery'),
           'never_arrived', 'Order never arrived',
           'The app says delivered but I never got my food.',
           'PackageMinus', 'never_arrived', 10),
          ((SELECT id FROM bu WHERE code='delivery'),
           'rider_late', 'Delivery was late',
           'The rider took much longer than the estimated time.',
           'Clock', 'rider_late', 20),
          ((SELECT id FROM bu WHERE code='delivery'),
           'rider_rude', 'Rider was rude',
           'The rider was rude or unprofessional at the door.',
           'UserX', 'rider_rude', 30),
          ((SELECT id FROM bu WHERE code='delivery'),
           'rider_demanded_tip', 'Rider demanded a tip',
           'The rider asked for extra money or refused to hand over the order.',
           'HandCoins', 'rider_demanded_tip', 40),

          ((SELECT id FROM bu WHERE code='payments'),
           'double_charge', 'Charged twice',
           'I was charged more than once for the same order.',
           'CreditCard', 'double_charge', 10),
          ((SELECT id FROM bu WHERE code='payments'),
           'promo_failed', 'Promo code did not apply',
           'My promo/discount code wasn''t applied at checkout.',
           'BadgePercent', 'promo_failed', 20),

          ((SELECT id FROM bu WHERE code='account'),
           'human_request', 'Talk to a person',
           'I''d like to speak with a real support agent.',
           'UserRound', 'human_request', 10),
          ((SELECT id FROM bu WHERE code='account'),
           'other', 'Something else',
           'None of the above — I''ll describe it.',
           'MessageSquareMore', 'other', 20);
        """
    )

    # -------- issue_type_data_points (per-issue data contract) --------
    # A macro table: which data points each issue type wants. Keeps the
    # enricher config-driven instead of hardcoded per intent.
    op.execute(
        """
        WITH i AS (SELECT id, code FROM issue_types),
             d AS (SELECT id, key FROM data_point_registry)
        INSERT INTO issue_type_data_points (issue_type_id, data_point_id, is_required, sort_order)
        SELECT i.id, d.id, true, sort_order FROM (VALUES
          -- Order-first ordering. Fetchers run in this order and can
          -- read from the growing context; order.customer_id and
          -- order.restaurant_id become available to the fetchers that
          -- follow, so the customer + restaurant lookups don't need an
          -- explicit hint.

          -- Order issues: order → customer → restaurant
          ('missing_item',   'order_full',          10),
          ('missing_item',   'customer_profile',    20),
          ('missing_item',   'restaurant_history',  30),
          ('wrong_order',    'order_full',          10),
          ('wrong_order',    'customer_profile',    20),
          ('wrong_order',    'restaurant_history',  30),
          ('cold_food',      'order_full',          10),
          ('cold_food',      'customer_profile',    20),
          ('cold_food',      'restaurant_history',  30),

          -- Delivery: adds rider + rider-incidents
          ('never_arrived',  'order_full',                  10),
          ('never_arrived',  'customer_profile',            20),
          ('never_arrived',  'rider_history',               30),
          ('never_arrived',  'rider_incidents_for_order',   40),
          ('never_arrived',  'customer_refunds_30d',        50),
          ('rider_late',     'order_full',                  10),
          ('rider_late',     'customer_profile',            20),
          ('rider_late',     'rider_history',               30),
          ('rider_rude',     'order_full',                  10),
          ('rider_rude',     'customer_profile',            20),
          ('rider_rude',     'rider_history',               30),
          ('rider_demanded_tip', 'order_full',              10),
          ('rider_demanded_tip', 'customer_profile',        20),
          ('rider_demanded_tip', 'rider_history',           30),

          -- Payments: adds refund history
          ('double_charge',  'order_full',          10),
          ('double_charge',  'customer_profile',    20),
          ('double_charge',  'customer_refunds_30d', 30),
          ('promo_failed',   'order_full',          10),
          ('promo_failed',   'customer_profile',    20),

          -- Account / other: just profile
          ('human_request',  'customer_profile',    10),
          ('other',          'customer_profile',    10)
        ) AS m(issue_code, dp_key, sort_order)
        JOIN i ON i.code = m.issue_code
        JOIN d ON d.key = m.dp_key;
        """
    )

    # -------- acknowledgment_templates --------
    # Three variations per issue type. Handlebars-style {{path}} against
    # the enriched context. Missing variables degrade gracefully at
    # render time — see app/conversation_studio/render.py.
    op.execute(
        """
        WITH i AS (SELECT id, code FROM issue_types)
        INSERT INTO acknowledgment_templates (issue_type_id, template, weight, is_active)
        SELECT i.id, t.template, t.weight, true FROM (VALUES
          ('missing_item',
           'Sorry to hear that, {{customer.first_name}}! Let me pull up your {{restaurant.name}} order to see what came short.', 1),
          ('missing_item',
           'Ugh, that''s frustrating. Give me a moment to look at order #{{order.id}} from {{restaurant.name}}.', 1),
          ('missing_item',
           'On it — checking your {{restaurant.name}} order now to see what''s missing.', 1),

          ('wrong_order',
           'That''s not what you paid for — let me pull up order #{{order.id}} and figure this out.', 1),
          ('wrong_order',
           'Sorry about the mixup, {{customer.first_name}}. Give me a sec on your {{restaurant.name}} order.', 1),
          ('wrong_order',
           'Looking into your {{restaurant.name}} order now — the wrong food is a real pain.', 1),

          ('cold_food',
           'Cold food is the worst — pulling up order #{{order.id}} from {{restaurant.name}}.', 1),
          ('cold_food',
           'Sorry, {{customer.first_name}}. Let me check the {{restaurant.name}} order.', 1),
          ('cold_food',
           'On it. Looking at your {{restaurant.name}} order to see what went wrong.', 1),

          ('never_arrived',
           'That''s really frustrating, {{customer.first_name}}. Let me check the delivery record on order #{{order.id}}.', 1),
          ('never_arrived',
           'I''m looking into your {{restaurant.name}} order — the rider''s status will tell us what actually happened.', 1),
          ('never_arrived',
           'Waiting for food and it never shows up is the worst. Give me a sec on order #{{order.id}}.', 1),

          ('rider_late',
           'Sorry about the wait, {{customer.first_name}}. Let me pull up the delivery details on order #{{order.id}}.', 1),
          ('rider_late',
           'Late deliveries are frustrating. Checking your {{restaurant.name}} order now.', 1),
          ('rider_late',
           'Give me a moment to look at what happened with your {{restaurant.name}} order.', 1),

          ('rider_rude',
           'Sorry you had to deal with that, {{customer.first_name}}. Let me check the rider on order #{{order.id}}.', 1),
          ('rider_rude',
           'That''s not okay at all. Pulling up the delivery details now.', 1),
          ('rider_rude',
           'Thanks for letting us know — checking on your {{restaurant.name}} order.', 1),

          ('rider_demanded_tip',
           'That''s absolutely not allowed. Let me look at the rider on order #{{order.id}}.', 1),
          ('rider_demanded_tip',
           'Riders can''t do that, {{customer.first_name}}. Give me a moment to pull up the case.', 1),
          ('rider_demanded_tip',
           'I''m sorry — that''s a real problem. Checking your {{restaurant.name}} delivery now.', 1),

          ('double_charge',
           'Double charges are always a bug on our side — let me pull up order #{{order.id}} to check.', 1),
          ('double_charge',
           'Sorry about that, {{customer.first_name}}. Looking at the payment on your order right now.', 1),
          ('double_charge',
           'On it — checking the transaction history for order #{{order.id}}.', 1),

          ('promo_failed',
           'Promo codes should just work. Let me check what happened with order #{{order.id}}.', 1),
          ('promo_failed',
           'That''s annoying, {{customer.first_name}}. Give me a sec to look at your order.', 1),
          ('promo_failed',
           'Looking at the promo code on your {{restaurant.name}} order now.', 1),

          ('human_request',
           'Sure thing, {{customer.first_name}}. Let me set that up.', 1),
          ('human_request',
           'No problem — connecting you with a colleague now.', 1),
          ('human_request',
           'On it. Bringing someone in to help.', 1),

          ('other',
           'Sure, {{customer.first_name}} — tell me a bit more and I''ll take a look.', 1),
          ('other',
           'Go ahead — what''s on your mind?', 1),
          ('other',
           'Happy to help. What''s going on?', 1)
        ) AS t(issue_code, template, weight)
        JOIN i ON i.code = t.issue_code;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_sessions_issue_type", table_name="sessions")
    op.drop_column("sessions", "business_unit_id")
    op.drop_column("sessions", "issue_type_id")
    op.drop_index("ix_intent_cases_lookup", table_name="intent_detection_cases")
    op.drop_table("intent_detection_cases")
    op.drop_index("ix_ack_templates_issue_type", table_name="acknowledgment_templates")
    op.drop_table("acknowledgment_templates")
    op.drop_table("issue_type_data_points")
    op.drop_index("ix_issue_types_routed_intent", table_name="issue_types")
    op.drop_index("ix_issue_types_bu", table_name="issue_types")
    op.drop_table("issue_types")
    op.drop_table("data_point_registry")
    op.drop_index("ix_business_units_parent", table_name="business_units")
    op.drop_table("business_units")
