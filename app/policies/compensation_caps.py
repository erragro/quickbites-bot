"""
Compensation caps — what can be auto-approved vs what needs a human.

Kirana Kart R-008 uses order-value brackets; the QuickBites policy hint
sets ₹1500 as the soft cap for non-gold customers. We combine both: a
bracket-based auto-approve ceiling, widened for gold-tier clean customers.

Pure Python, pure functions — no I/O.
"""

from __future__ import annotations

from typing import Optional

from app.policies.abuse_rules import has_clean_history
from app.schemas import CustomerProfile


def auto_approve_cap(
    *, order_total_inr: Optional[int], customer: Optional[CustomerProfile]
) -> int:
    """Return the ₹ ceiling under which a refund auto-approves.

    Above this, Stage 2 downgrades to `escalate_to_human`. Brackets mirror
    Kirana Kart R-008 (auto-approved tiers only); gold + clean customers get
    the next tier's ceiling per R-005.
    """
    if order_total_inr is None:
        return 500  # no order context → very conservative

    gold_clean = bool(
        customer
        and customer.loyalty_tier == "gold"
        and has_clean_history(customer.abuse)
    )

    # Bracket: (upper_bound_of_order_total, base_cap, gold_cap)
    brackets = [
        (200, 300, 500),
        (500, 650, 900),
        (1000, 1200, 1600),
        (2000, 1500, 2250),
        (5000, 1500, 3500),
    ]
    for upper, base_cap, gold_cap in brackets:
        if order_total_inr <= upper:
            return gold_cap if gold_clean else base_cap

    # > ₹5000 orders: bot never auto-approves.
    return 3500 if gold_clean else 1500


def within_cap(
    *,
    refund_total_inr: int,
    order_total_inr: Optional[int],
    customer: Optional[CustomerProfile],
) -> bool:
    return refund_total_inr <= auto_approve_cap(
        order_total_inr=order_total_inr, customer=customer
    )
