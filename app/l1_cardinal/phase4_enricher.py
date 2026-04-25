"""
Phase 4 Enricher — pull everything the LLM might need from Postgres in one shot.
Stage 1 still has live tools for re-querying, but the eager pre-fetch means
the model usually doesn't need to make tool calls for the common path, which
saves a round-trip and keeps latency down.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app import repository
from app.schemas import EnrichedContext


def run(
    db: Session,
    *,
    order_id: int | None,
    customer_id: int | None,
) -> EnrichedContext:
    ctx = EnrichedContext()

    if order_id is not None:
        ctx.order = repository.fetch_order(db, order_id)
        if ctx.order:
            customer_id = customer_id or ctx.order.customer_id
            if ctx.order.rider_id:
                ctx.rider = repository.fetch_rider_history(db, ctx.order.rider_id)
            ctx.restaurant = repository.fetch_restaurant_history(
                db, ctx.order.restaurant_id
            )

    if customer_id is not None:
        ctx.customer = repository.fetch_customer(db, customer_id)

    return ctx
