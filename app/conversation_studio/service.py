"""
Chip-tap chatbot primitives — pure functions on top of the ORM.

Two responsibilities:
  1. Enrich context for a chip tap based on the issue type's declared
     data points (`resolve_data_points`).
  2. Pick and render an acknowledgment template against that context
     (`pick_and_render_ack`).

Kept HTTP-free so both the public chip endpoint and the future admin
CRUD panel can call the same primitives.
"""

from __future__ import annotations

import logging
import random
import uuid
from typing import Any, Callable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import repository
from app.conversation_studio.render import render
from app.models import (
    AcknowledgmentTemplate,
    IssueType,
    IssueTypeDataPoint,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Fetcher registry
#
# Maps the string in data_point_registry.fetcher_ref to an actual Python
# callable. Admin panel can only PICK from these — they can't add new
# ones (that's code). Each fetcher takes (db, ctx, hints) and returns
# either (context_key, data_dict) or None (if it couldn't resolve).
#
# Order matters at call-time: fetchers that produce entities other
# fetchers depend on should run first (order → gives restaurant_id +
# rider_id → then restaurant + rider fetchers can pick those up from
# `ctx` on subsequent iterations).
# ---------------------------------------------------------------------------


FetcherResult = Optional[tuple[str, dict[str, Any]]]
Fetcher = Callable[..., FetcherResult]


def _customer_dict(profile) -> dict[str, Any]:
    """Convert a CustomerProfile to a template-friendly dict. Splits
    `name` into first_name / last_name so templates can address the
    customer casually."""
    if profile is None:
        return {}
    d = profile.model_dump()
    name = d.get("name") or ""
    parts = name.split(maxsplit=1)
    d["first_name"] = parts[0] if parts else ""
    d["last_name"] = parts[1] if len(parts) > 1 else ""
    return d


def _fetch_customer(db, ctx, order_id, customer_id):
    cid = customer_id or ctx.get("order", {}).get("customer_id")
    if not cid:
        return None
    profile = repository.fetch_customer(db, cid)
    if profile is None:
        return None
    return "customer", _customer_dict(profile)


def _fetch_order(db, ctx, order_id, customer_id):
    if not order_id:
        return None
    order = repository.fetch_order(db, order_id)
    if order is None:
        return None
    return "order", order.model_dump()


def _fetch_restaurant(db, ctx, order_id, customer_id):
    rid = ctx.get("order", {}).get("restaurant_id")
    if not rid:
        return None
    r = repository.fetch_restaurant_history(db, rid)
    if r is None:
        return None
    return "restaurant", r.model_dump()


def _fetch_rider(db, ctx, order_id, customer_id):
    rid = ctx.get("order", {}).get("rider_id")
    if not rid:
        return None
    r = repository.fetch_rider_history(db, rid)
    if r is None:
        return None
    return "rider", r.model_dump()


def _fetch_customer_complaints(db, ctx, order_id, customer_id):
    cid = customer_id or ctx.get("order", {}).get("customer_id")
    if not cid:
        return None
    rows = repository.fetch_customer_complaints(db, cid, limit=10)
    return "recent_complaints", {"count": len(rows), "items": rows}


def _fetch_customer_refunds(db, ctx, order_id, customer_id):
    cid = customer_id or ctx.get("order", {}).get("customer_id")
    if not cid:
        return None
    rows = repository.fetch_customer_refunds(db, cid, since_days=30)
    total = sum(r.get("amount_inr") or 0 for r in rows)
    return "recent_refunds", {
        "count": len(rows),
        "total_inr": total,
        "items": rows,
    }


def _fetch_rider_incidents_for_order(db, ctx, order_id, customer_id):
    if not order_id:
        return None
    rows = repository.fetch_rider_incidents_for_order(db, order_id)
    return "rider_incidents", {"count": len(rows), "items": rows}


FETCHER_REGISTRY: dict[str, Fetcher] = {
    # DB fetcher_ref → callable. Keep the string keys stable across
    # deploys since they're stored in data_point_registry rows.
    "repository.fetch_customer_full": _fetch_customer,
    "repository.fetch_order_full": _fetch_order,
    "repository.fetch_restaurant_full": _fetch_restaurant,
    "repository.fetch_rider_full": _fetch_rider,
    "repository.fetch_customer_complaints": _fetch_customer_complaints,
    "repository.fetch_customer_refunds": _fetch_customer_refunds,
    "repository.fetch_rider_incidents_for_order": _fetch_rider_incidents_for_order,
}


# ---------------------------------------------------------------------------
# Load issue type + resolve data points
# ---------------------------------------------------------------------------


def load_issue_type_full(
    db: Session, issue_type_id: uuid.UUID,
) -> Optional[IssueType]:
    """Load an IssueType with its data-point bindings + registry rows +
    active templates in one query. Returns None if missing/inactive."""
    row = db.execute(
        select(IssueType)
        .options(
            selectinload(IssueType.data_point_links).selectinload(
                IssueTypeDataPoint.data_point,
            ),
        )
        .where(IssueType.id == issue_type_id, IssueType.is_active.is_(True))
    ).scalar_one_or_none()
    return row


def resolve_data_points(
    db: Session,
    issue_type: IssueType,
    *,
    order_id: Optional[int] = None,
    customer_id: Optional[int] = None,
) -> tuple[dict[str, Any], list[str]]:
    """
    Run the fetchers declared for this issue type. Later fetchers can
    read from `ctx` populated by earlier ones (order runs first so
    restaurant / rider can pick their IDs off it).

    Returns (context_dict, list_of_resolved_data_point_keys). The
    caller feeds `context_dict` into template rendering and forwards
    the list to the frontend so the UI can decide whether to prompt
    the user for missing inputs (e.g. "please tell me your order
    number").
    """
    ctx: dict[str, Any] = {}
    resolved: list[str] = []

    # sort_order was already applied by the eager-load's order_by;
    # respect it here so admins can control fetcher ordering from the UI.
    for link in issue_type.data_point_links:
        dp = link.data_point
        fetcher = FETCHER_REGISTRY.get(dp.fetcher_ref)
        if fetcher is None:
            logger.warning(
                "no fetcher for %r (issue_type=%s data_point=%s) — skipping",
                dp.fetcher_ref, issue_type.code, dp.key,
            )
            continue
        try:
            result = fetcher(db, ctx, order_id, customer_id)
        except Exception:  # noqa: BLE001
            logger.exception(
                "fetcher %r crashed for issue_type=%s data_point=%s",
                dp.fetcher_ref, issue_type.code, dp.key,
            )
            continue
        if result is None:
            continue
        key, data = result
        ctx[key] = data
        resolved.append(dp.key)
    return ctx, resolved


# ---------------------------------------------------------------------------
# Pick + render acknowledgment template
# ---------------------------------------------------------------------------


def pick_template(db: Session, issue_type_id: uuid.UUID) -> Optional[str]:
    """Weighted-random pick from active templates for this issue type."""
    rows = db.execute(
        select(AcknowledgmentTemplate).where(
            AcknowledgmentTemplate.issue_type_id == issue_type_id,
            AcknowledgmentTemplate.is_active.is_(True),
        )
    ).scalars().all()
    if not rows:
        return None
    # random.choices supports weights natively; total-zero weights would
    # raise, so treat any non-positive weight as 1 to keep the pool alive.
    weights = [max(1, r.weight) for r in rows]
    return random.choices(rows, weights=weights, k=1)[0].template


def pick_and_render_ack(
    db: Session,
    issue_type_id: uuid.UUID,
    context: dict[str, Any],
) -> str:
    """
    Full ack path: pick a variant, substitute variables. Guarantees a
    non-empty return — falls back to a neutral phrase if no templates
    are configured (misconfiguration, not a runtime bug).
    """
    template = pick_template(db, issue_type_id)
    if template is None:
        return "Got it — let me pull up the details."
    return render(template, context)
