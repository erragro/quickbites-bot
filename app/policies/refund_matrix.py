"""
Refund amount matrix — the deterministic core that turns an (intent, order,
customer) triple into a concrete refund proposal.

Modelled on the production Kirana Kart R-007 / TIER-002 tables: each intent
maps to a base refund percentage of the affected portion, with a complaint
target and refund method. A customer-tier multiplier adjusts the base value,
clamped to the band specified in Kirana Kart's TIER-002.

Kept as pure Python — no I/O, no LLM. Stage 2 calls this directly when Stage
1 either (a) didn't propose a concrete fix despite refundable data being
present, or (b) proposed an amount that disagreed with the matrix by more
than a noise threshold. Leaving the LLM to re-derive these numbers from
prose every turn was the single biggest source of `refund_correct` failures
on the prod eval.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.schemas import (
    AbuseSignals,
    ComplaintTarget,
    CustomerProfile,
    Intent,
    OrderContext,
    RefundMethod,
)


@dataclass(frozen=True)
class MatrixEntry:
    """One row of the refund decision table."""

    base_pct: float  # fraction of order total (0.0 = no refund)
    method: Optional[RefundMethod]  # None = no refund at all
    complaint_target: Optional[ComplaintTarget]  # None = no complaint
    min_inr: int = 0  # floor amount if base_pct*total is too low
    label: str = ""


_MATRIX: dict[Intent, MatrixEntry] = {
    # Food / order issues against the restaurant
    "missing_item": MatrixEntry(
        base_pct=0.50, method="wallet_credit", complaint_target="restaurant",
        min_inr=50, label="missing_item:partial",
    ),
    "wrong_order": MatrixEntry(
        base_pct=1.00, method="wallet_credit", complaint_target="restaurant",
        label="wrong_order:full",
    ),
    "cold_food": MatrixEntry(
        base_pct=0.30, method="wallet_credit", complaint_target="restaurant",
        min_inr=50, label="cold_food:partial",
    ),
    # Rider issues — money only when the order itself failed
    "never_arrived": MatrixEntry(
        base_pct=1.00, method="wallet_credit", complaint_target="rider",
        label="never_arrived:full",
    ),
    "rider_late": MatrixEntry(
        base_pct=0.10, method="wallet_credit", complaint_target="rider",
        min_inr=50, label="rider_late:gesture",
    ),
    "rider_rude": MatrixEntry(
        base_pct=0.0, method=None, complaint_target="rider",
        label="rider_rude:complaint_only",
    ),
    "rider_demanded_tip": MatrixEntry(
        base_pct=0.0, method=None, complaint_target="rider",
        label="rider_demanded_tip:complaint_only",
    ),
    # App / platform issues
    "double_charge": MatrixEntry(
        base_pct=0.0, method=None, complaint_target="app",
        label="double_charge:engineering",
    ),
    "promo_failed": MatrixEntry(
        base_pct=0.10, method="wallet_credit", complaint_target="app",
        min_inr=50, label="promo_failed:wallet_credit",
    ),
    # Non-actionable by matrix
    "cancel_request": MatrixEntry(
        base_pct=0.0, method=None, complaint_target=None, label="cancel_request:noop",
    ),
    "human_request": MatrixEntry(
        base_pct=0.0, method=None, complaint_target=None, label="human_request:noop",
    ),
    "vague": MatrixEntry(
        base_pct=0.0, method=None, complaint_target=None, label="vague:noop",
    ),
    "other": MatrixEntry(
        base_pct=0.0, method=None, complaint_target=None, label="other:noop",
    ),
}


def _tier_multiplier(customer: Optional[CustomerProfile]) -> float:
    """Mirror Kirana Kart TIER-002 — clamp to [0.5, 1.3]."""
    if customer is None:
        return 1.0
    mult = 1.0
    if customer.loyalty_tier == "gold":
        mult += 0.15
    if customer.abuse.total_orders > 100:
        mult += 0.10
    if customer.abuse.is_likely_abuser:
        mult -= 0.30
    return max(0.5, min(1.3, mult))


@dataclass
class MatrixProposal:
    refund_inr: int  # 0 = no refund
    method: Optional[RefundMethod]
    complaint_target: Optional[ComplaintTarget]
    label: str
    multiplier_applied: float


def propose(
    *,
    intent: Intent,
    order: Optional[OrderContext],
    customer: Optional[CustomerProfile],
) -> Optional[MatrixProposal]:
    """Return the matrix's concrete proposal for this (intent, order, customer).

    Returns None when the matrix has nothing useful to contribute — caller
    falls back to Stage 1's advisory output. Concretely this means: the
    intent isn't in the matrix, or the order is missing (can't compute an
    amount without a total), or the entry explicitly says "no refund and no
    complaint."
    """
    entry = _MATRIX.get(intent)
    if entry is None:
        return None

    # No order → no money; caller decides on complaint separately if the
    # entry has a target, but most complaint actions need an order_id too.
    if order is None:
        if entry.complaint_target is None:
            return None
        return MatrixProposal(
            refund_inr=0,
            method=None,
            complaint_target=entry.complaint_target,
            label=entry.label + ":no_order",
            multiplier_applied=1.0,
        )

    multiplier = _tier_multiplier(customer)

    base_amount = int(round(order.total_inr * entry.base_pct))
    if entry.base_pct > 0 and base_amount < entry.min_inr:
        base_amount = min(entry.min_inr, order.total_inr)

    final_amount = int(round(base_amount * multiplier))
    # Hard cap at order total — defence-in-depth, Stage 2 also caps.
    final_amount = min(final_amount, order.total_inr)

    if entry.base_pct == 0 and entry.complaint_target is None:
        return None

    return MatrixProposal(
        refund_inr=final_amount if entry.method else 0,
        method=entry.method if final_amount > 0 else None,
        complaint_target=entry.complaint_target,
        label=entry.label,
        multiplier_applied=multiplier,
    )


def is_refundable_intent(intent: Intent) -> bool:
    """Intents where the matrix can issue money (for Stage 1 prompt guidance)."""
    entry = _MATRIX.get(intent)
    return bool(entry and entry.base_pct > 0)
