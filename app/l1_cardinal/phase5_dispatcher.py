"""
Phase 5 Dispatcher — synchronous version. Mints execution_id, assigns a
priority + escalation_group, persists a bot_executions row. No stream push —
the next call (into the 4-stage LLM pipeline) *is* the dispatch.

Tag set is deliberately identical to kirana_kart Cardinal so the lineage is
visible in logs and the design doc.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas import EnrichedContext, EscalationGroup, Priority


@dataclass
class DispatchResult:
    execution_id: str
    escalation_group: EscalationGroup
    priority: Priority


def _priority_for(group: EscalationGroup) -> Priority:
    return {
        "FRAUD_REVIEW": "CRITICAL",
        "VIP_CONCIERGE": "HIGH",
        "REPEAT_ESCALATION": "HIGH",
        "STANDARD": "STANDARD",
    }[group]


def _classify(ctx: EnrichedContext) -> EscalationGroup:
    customer = ctx.customer

    if customer and customer.abuse.is_likely_abuser:
        return "FRAUD_REVIEW"

    if customer and customer.loyalty_tier == "gold":
        return "VIP_CONCIERGE"

    if customer and customer.abuse.total_complaints >= 3:
        # heuristic for "repeat" — treat customers with >=3 lifetime complaints
        # or a high-rejection history as repeat-escalation.
        if customer.abuse.rejected_complaint_rate > 0.25:
            return "REPEAT_ESCALATION"

    return "STANDARD"


def run(
    db: Session,
    *,
    session_id: str,
    turn_no: int,
    ctx: EnrichedContext,
) -> DispatchResult:
    group = _classify(ctx)
    priority = _priority_for(group)

    execution_id = (
        f"quickbites_{session_id[:16]}_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    )

    db.execute(
        text(
            """
            INSERT INTO bot_executions (execution_id, session_id, turn_no, escalation_group, priority)
            VALUES (:eid, :sid, :t, :grp, :prio)
            """
        ),
        {
            "eid": execution_id,
            "sid": session_id,
            "t": turn_no,
            "grp": group,
            "prio": priority,
        },
    )
    db.commit()

    return DispatchResult(
        execution_id=execution_id,
        escalation_group=group,
        priority=priority,
    )
