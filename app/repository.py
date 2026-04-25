"""
Thin data-access layer. Both the Phase 4 Enricher and Stage 1 tools call into
this. Queries mirror sample_queries.sql where possible; all 'recent' math is
pinned to DATA_TODAY (2026-04-13) per schema.md.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import DATA_TODAY
from app.policies.abuse_rules import compute_abuse_signals
from app.schemas import (
    AbuseSignals,
    CustomerProfile,
    OrderContext,
    RestaurantHistory,
    RiderHistory,
)


def _row_to_dict(row) -> dict:
    return dict(row._mapping) if row is not None else {}


def fetch_order(db: Session, order_id: int) -> Optional[OrderContext]:
    row = db.execute(
        text("SELECT * FROM orders WHERE id = :id"),
        {"id": order_id},
    ).first()
    if not row:
        return None
    order = _row_to_dict(row)

    items = [
        _row_to_dict(r)
        for r in db.execute(
            text("SELECT item_name, qty, price_inr FROM order_items WHERE order_id = :id"),
            {"id": order_id},
        )
    ]
    return OrderContext(**order, items=items)


def _customer_aggregates(db: Session, customer_id: int) -> dict:
    orders = db.execute(
        text("SELECT count(*) FROM orders WHERE customer_id = :id"),
        {"id": customer_id},
    ).scalar_one()

    complaint_row = db.execute(
        text(
            """
            SELECT count(*) AS total,
                   sum(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) AS rejected
            FROM complaints WHERE customer_id = :id
            """
        ),
        {"id": customer_id},
    ).first()
    total_complaints = complaint_row.total or 0
    rejected = complaint_row.rejected or 0

    window_start = (DATA_TODAY - timedelta(days=30)).isoformat()
    refund_row = db.execute(
        text(
            """
            SELECT count(*) AS n, coalesce(sum(amount_inr), 0) AS total
            FROM refunds
            WHERE customer_id = :id AND issued_at >= :since
            """
        ),
        {"id": customer_id, "since": window_start},
    ).first()

    return {
        "total_orders": orders,
        "total_complaints": total_complaints,
        "rejected_complaints": rejected,
        "refunds_30d_count": refund_row.n or 0,
        "refunds_30d_total_inr": refund_row.total or 0,
    }


def fetch_customer(db: Session, customer_id: int) -> Optional[CustomerProfile]:
    row = db.execute(
        text("SELECT * FROM customers WHERE id = :id"),
        {"id": customer_id},
    ).first()
    if not row:
        return None
    c = _row_to_dict(row)
    agg = _customer_aggregates(db, customer_id)
    signals: AbuseSignals = compute_abuse_signals(
        joined_at=c.get("joined_at"),
        total_orders=agg["total_orders"],
        total_complaints=agg["total_complaints"],
        rejected_complaints=agg["rejected_complaints"],
        refunds_30d_count=agg["refunds_30d_count"],
        refunds_30d_total_inr=agg["refunds_30d_total_inr"],
    )
    return CustomerProfile(
        id=c["id"],
        name=c["name"],
        loyalty_tier=c.get("loyalty_tier") or "bronze",
        wallet_balance_inr=c.get("wallet_balance_inr") or 0,
        city=c.get("city") or "",
        joined_at=c.get("joined_at") or "",
        abuse=signals,
    )


def fetch_rider_history(db: Session, rider_id: int) -> Optional[RiderHistory]:
    row = db.execute(
        text("SELECT * FROM riders WHERE id = :id"),
        {"id": rider_id},
    ).first()
    if not row:
        return None
    r = _row_to_dict(row)

    counts = db.execute(
        text(
            """
            SELECT sum(CASE WHEN verified=1 THEN 1 ELSE 0 END) AS v,
                   sum(CASE WHEN verified=0 THEN 1 ELSE 0 END) AS u
            FROM rider_incidents WHERE rider_id = :id
            """
        ),
        {"id": rider_id},
    ).first()
    types_seen = [
        row.type
        for row in db.execute(
            text(
                "SELECT DISTINCT type FROM rider_incidents "
                "WHERE rider_id = :id ORDER BY type"
            ),
            {"id": rider_id},
        )
    ]
    return RiderHistory(
        id=r["id"],
        name=r["name"],
        joined_at=r.get("joined_at") or "",
        verified_incidents=counts.v or 0,
        unverified_incidents=counts.u or 0,
        types_seen=types_seen,
    )


def fetch_restaurant_history(db: Session, restaurant_id: int) -> Optional[RestaurantHistory]:
    row = db.execute(
        text("SELECT * FROM restaurants WHERE id = :id"),
        {"id": restaurant_id},
    ).first()
    if not row:
        return None
    r = _row_to_dict(row)

    stats = db.execute(
        text(
            """
            SELECT avg(rating)::float AS avg_rating, count(*) AS n
            FROM reviews WHERE restaurant_id = :id
            """
        ),
        {"id": restaurant_id},
    ).first()

    complaint_count = db.execute(
        text(
            """
            SELECT count(*) FROM complaints
            WHERE target_type = 'restaurant' AND target_id = :id
            """
        ),
        {"id": restaurant_id},
    ).scalar_one()

    return RestaurantHistory(
        id=r["id"],
        name=r["name"],
        cuisine=r.get("cuisine") or "",
        avg_rating=round(stats.avg_rating, 2) if stats.avg_rating is not None else None,
        n_reviews=stats.n or 0,
        recent_complaint_count=complaint_count,
    )


def fetch_customer_complaints(db: Session, customer_id: int, limit: int = 10) -> list[dict]:
    return [
        _row_to_dict(r)
        for r in db.execute(
            text(
                """
                SELECT id, order_id, target_type, target_id, raised_at,
                       description, status, resolution, resolution_amount_inr
                FROM complaints WHERE customer_id = :id
                ORDER BY raised_at DESC LIMIT :lim
                """
            ),
            {"id": customer_id, "lim": limit},
        )
    ]


def fetch_customer_refunds(db: Session, customer_id: int, since_days: int = 30) -> list[dict]:
    since = (DATA_TODAY - timedelta(days=since_days)).isoformat()
    return [
        _row_to_dict(r)
        for r in db.execute(
            text(
                """
                SELECT id, order_id, amount_inr, type, issued_at, reason
                FROM refunds
                WHERE customer_id = :id AND issued_at >= :since
                ORDER BY issued_at DESC
                """
            ),
            {"id": customer_id, "since": since},
        )
    ]


def fetch_rider_incidents_for_order(db: Session, order_id: int) -> list[dict]:
    return [
        _row_to_dict(r)
        for r in db.execute(
            text(
                """
                SELECT id, rider_id, type, reported_at, verified, notes
                FROM rider_incidents WHERE order_id = :id
                """
            ),
            {"id": order_id},
        )
    ]
