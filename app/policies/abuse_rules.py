"""
Pure functions that turn DB aggregates into abuse signals. No I/O here —
all inputs are plain values so the logic is trivially unit-testable.

The thresholds are deliberately conservative. Policy hints (policy_and_faq.md)
tell us to watch for high complaint-rate-with-rejections, brand-new accounts
with many complaints, and refund-flooding in the last 30 days.
"""

from __future__ import annotations

from datetime import date, datetime

from app.config import DATA_TODAY
from app.schemas import AbuseSignals


def _parse_iso_date(ts: str | None) -> date | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def compute_abuse_signals(
    *,
    joined_at: str | None,
    total_orders: int,
    total_complaints: int,
    rejected_complaints: int,
    refunds_30d_count: int,
    refunds_30d_total_inr: int,
) -> AbuseSignals:
    joined = _parse_iso_date(joined_at)
    age_days = (DATA_TODAY - joined).days if joined else 0

    complaint_rate = (total_complaints / total_orders) if total_orders else 0.0
    rejected_rate = (rejected_complaints / total_complaints) if total_complaints else 0.0

    reasons: list[str] = []

    brand_new_complainer = age_days < 30 and total_complaints >= 2
    if brand_new_complainer:
        reasons.append(
            f"account_age={age_days}d with {total_complaints} complaints"
        )

    high_rate_high_rejection = complaint_rate > 0.5 and rejected_rate > 0.5
    if high_rate_high_rejection:
        reasons.append(
            f"complaint_rate={complaint_rate:.2f} rejected_rate={rejected_rate:.2f}"
        )

    # `refunds_30d_total_inr > 2000` alone trips legitimate high-spend
    # customers (gold-tier, no rejections, normal complaint pattern). The
    # money signal is meaningful only with a corroborating signal: at
    # least one prior rejection, or 4+ refund events in the window. Bare
    # high spend → don't flag.
    refund_flooded = (
        refunds_30d_total_inr > 2000
        and (rejected_rate > 0 or refunds_30d_count >= 4)
    )
    if refund_flooded:
        reasons.append(
            f"refunds_30d=₹{refunds_30d_total_inr} over {refunds_30d_count} events"
        )

    is_abuser = bool(reasons)

    return AbuseSignals(
        complaint_rate=round(complaint_rate, 3),
        rejected_complaint_rate=round(rejected_rate, 3),
        refunds_30d_count=refunds_30d_count,
        refunds_30d_total_inr=refunds_30d_total_inr,
        account_age_days=age_days,
        total_orders=total_orders,
        total_complaints=total_complaints,
        is_likely_abuser=is_abuser,
        abuse_reasons=reasons,
    )


def has_clean_history(signals: AbuseSignals) -> bool:
    return (
        not signals.is_likely_abuser
        and signals.complaint_rate <= 0.3
        and signals.rejected_complaint_rate == 0.0
    )
