"""
Cardinal-inspired synchronous pipeline orchestrator.

One call per customer turn. Runs Phase 1–5 then Stage 0–3 in sequence inside a
single Postgres session. Returns a reply envelope ready to hand to the
simulator via simulator_client.reply().

Any exception inside Stage 0–3 is caught and converted to a conservative
"escalate_to_human" response so we never fail the whole session on a single
flaky turn.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text as sql_text
from sqlalchemy.orm import Session

from app.l1_cardinal import (
    phase1_validator,
    phase2_deduplicator,
    phase3_handler,
    phase4_enricher,
    phase5_dispatcher,
)
from app.l2_agents import (
    stage0_classifier,
    stage1_evaluator,
    stage2_validator,
    stage3_responder,
)
from app.schemas import ProposedAction


logger = logging.getLogger(__name__)


@dataclass
class TurnResult:
    bot_message: str
    actions: list[dict]
    classification: dict
    reasoning: str
    route: str
    escalation_group: str
    execution_id: str
    overrides: list[str]
    stage_timings_ms: dict[str, int]
    from_cache: bool = False


def _history_snippet(history, limit: int = 8) -> str:
    tail = history[-limit:]
    lines = []
    for t in tail:
        label = "Customer" if t.role == "customer" else "Agent"
        line = f"{label}: {t.message}"
        if t.role == "bot" and t.actions:
            types = sorted({str(a.get("type", "")) for a in t.actions})
            line += f"  [actions={','.join(x for x in types if x)}]"
        lines.append(line)
    return "\n".join(lines)


def _persist_turn(
    db: Session,
    *,
    session_id: str,
    turn_no: int,
    role: str,
    message: str,
    classification: dict | None,
    actions: list[dict] | None,
    reasoning: str | None,
    route: str | None,
    escalation_group: str | None,
    execution_id: str | None,
    stage_timings_ms: dict | None,
) -> None:
    db.execute(
        sql_text(
            """
            INSERT INTO turns (
                session_id, turn_no, role, message,
                classification, actions, reasoning,
                route, escalation_group, execution_id, stage_timings_ms
            ) VALUES (
                :sid, :t, :role, :msg,
                :cls, :act, :reason,
                :route, :grp, :eid, :timings
            )
            """
        ),
        {
            "sid": session_id,
            "t": turn_no,
            "role": role,
            "msg": message,
            "cls": json.dumps(classification) if classification is not None else None,
            "act": json.dumps(actions) if actions is not None else None,
            "reason": reasoning,
            "route": route,
            "grp": escalation_group,
            "eid": execution_id,
            "timings": json.dumps(stage_timings_ms) if stage_timings_ms is not None else None,
        },
    )
    db.commit()


def _safe_fallback() -> tuple[str, list[dict]]:
    msg = (
        "Thanks for reaching out — I'm looping in a colleague who can take a closer "
        "look at this for you. You'll hear back shortly."
    )
    actions = [
        {
            "type": "escalate_to_human",
            "reason": "Pipeline caught an internal error; conservative escalation.",
        }
    ]
    return msg, actions


def run_turn(
    db: Session,
    *,
    session_id: str,
    customer_message: str,
    simulator_session_id: str | None = None,
    mode: str = "dev",
    scenario_id: int | None = None,
    max_turns: int | None = None,
) -> TurnResult:
    timings: dict[str, int] = {}
    t0 = time.perf_counter()

    # ------ Phase 1: Validator ------
    v = phase1_validator.run(customer_message)
    timings["phase1_validator"] = int((time.perf_counter() - t0) * 1000)
    if not v.passed:
        bot_message, actions = _safe_fallback()
        return TurnResult(
            bot_message=bot_message,
            actions=actions,
            classification={"intent": "vague", "validator_failure": v.failure_reason},
            reasoning=f"Validator rejected input: {v.failure_reason}",
            route="HITL",
            escalation_group="STANDARD",
            execution_id="validator_rejected",
            overrides=["validator_failure"],
            stage_timings_ms=timings,
        )

    message = v.message
    injection_flag = v.injection_attempt
    verbal_abuse = v.verbal_abuse

    # ------ Phase 2: Deduplicator ------
    t_start = time.perf_counter()
    cached = phase2_deduplicator.lookup(session_id, message)
    timings["phase2_deduplicator"] = int((time.perf_counter() - t_start) * 1000)
    if cached:
        logger.info("pipeline dedup hit session=%s", session_id)
        session = phase3_handler.load_or_create(
            db,
            session_id=session_id,
            simulator_session_id=simulator_session_id,
            mode=mode,
            scenario_id=scenario_id,
            max_turns=max_turns,
        )
        _persist_turn(
            db,
            session_id=session_id,
            turn_no=session.turn_no,
            role="customer",
            message=message,
            classification={"dedup_hit": True},
            actions=None,
            reasoning=None,
            route=None,
            escalation_group=None,
            execution_id=None,
            stage_timings_ms=timings,
        )
        _persist_turn(
            db,
            session_id=session_id,
            turn_no=session.turn_no,
            role="bot",
            message=cached.bot_message,
            classification=None,
            actions=cached.actions,
            reasoning="dedup_replay",
            route="AUTO_RESOLVED",
            escalation_group="STANDARD",
            execution_id=None,
            stage_timings_ms=timings,
        )
        return TurnResult(
            bot_message=cached.bot_message,
            actions=cached.actions,
            classification={"dedup_hit": True},
            reasoning="dedup_replay",
            route="AUTO_RESOLVED",
            escalation_group="STANDARD",
            execution_id="dedup_replay",
            overrides=[],
            stage_timings_ms=timings,
            from_cache=True,
        )

    # ------ Phase 3: Handler ------
    t_start = time.perf_counter()
    session = phase3_handler.load_or_create(
        db,
        session_id=session_id,
        simulator_session_id=simulator_session_id,
        mode=mode,
        scenario_id=scenario_id,
        max_turns=max_turns,
    )
    timings["phase3_handler"] = int((time.perf_counter() - t_start) * 1000)
    history_snippet = _history_snippet(session.history)

    # Persist the customer turn up front (pre-LLM) so we can audit even on crashes.
    _persist_turn(
        db,
        session_id=session_id,
        turn_no=session.turn_no,
        role="customer",
        message=message,
        classification=None,
        actions=None,
        reasoning=None,
        route=None,
        escalation_group=None,
        execution_id=None,
        stage_timings_ms=None,
    )

    try:
        # ------ Stage 0: Classify ------
        t_start = time.perf_counter()
        classification = stage0_classifier.classify(
            message, history_snippet=history_snippet
        )
        timings["stage0_classify"] = int((time.perf_counter() - t_start) * 1000)

        if classification.mentioned_order_id and session.known_order_id is None:
            phase3_handler.update_known_ids(
                db, session_id, order_id=classification.mentioned_order_id
            )
            session.known_order_id = classification.mentioned_order_id

        # ------ Phase 4: Enrich ------
        t_start = time.perf_counter()
        ctx = phase4_enricher.run(
            db,
            order_id=session.known_order_id or classification.mentioned_order_id,
            customer_id=session.known_customer_id,
        )
        if ctx.order and session.known_customer_id is None:
            phase3_handler.update_known_ids(db, session_id, customer_id=ctx.order.customer_id)
            session.known_customer_id = ctx.order.customer_id
        timings["phase4_enrich"] = int((time.perf_counter() - t_start) * 1000)

        # ------ Phase 5: Dispatch ------
        t_start = time.perf_counter()
        dispatch = phase5_dispatcher.run(
            db, session_id=session_id, turn_no=session.turn_no, ctx=ctx
        )
        timings["phase5_dispatch"] = int((time.perf_counter() - t_start) * 1000)

        already_escalated = session.already_escalated
        prior_bot_message = session.prior_bot_message

        # ------ Stage 1: Evaluate ------
        t_start = time.perf_counter()
        stage1 = stage1_evaluator.evaluate(
            db,
            customer_message=message,
            history_snippet=history_snippet,
            classification=classification,
            ctx=ctx,
            escalation_group=dispatch.escalation_group,
            injection_flag=injection_flag,
            verbal_abuse=verbal_abuse,
            already_escalated=already_escalated,
            prior_bot_message=prior_bot_message,
            turn_no=session.turn_no,
        )
        timings["stage1_evaluate"] = int((time.perf_counter() - t_start) * 1000)

        # ------ Stage 2: Validate ------
        t_start = time.perf_counter()
        stage2 = stage2_validator.validate(
            stage1=stage1,
            classification=classification,
            ctx=ctx,
            injection_flag=injection_flag,
            verbal_abuse=verbal_abuse,
            turn_no=session.turn_no,
            already_escalated=already_escalated,
            customer_message=customer_message,
            prior_bot_actions=session.prior_bot_actions,
            already_flag_abused=session.already_flag_abused,
        )
        timings["stage2_validate"] = int((time.perf_counter() - t_start) * 1000)

        # ------ Stage 3: Respond ------
        t_start = time.perf_counter()
        stage3 = stage3_responder.respond(
            customer_message=message,
            history_snippet=history_snippet,
            classification=classification,
            ctx=ctx,
            final_actions=stage2.final_actions,
            prior_bot_message=prior_bot_message,
            already_escalated=already_escalated,
        )
        timings["stage3_respond"] = int((time.perf_counter() - t_start) * 1000)

        phase2_deduplicator.remember(session_id, message, stage3.bot_message, stage3.actions)

        _persist_turn(
            db,
            session_id=session_id,
            turn_no=session.turn_no,
            role="bot",
            message=stage3.bot_message,
            classification=classification.model_dump(),
            actions=stage3.actions,
            reasoning=stage1.reasoning,
            route=stage2.route,
            escalation_group=dispatch.escalation_group,
            execution_id=dispatch.execution_id,
            stage_timings_ms=timings,
        )

        return TurnResult(
            bot_message=stage3.bot_message,
            actions=stage3.actions,
            classification=classification.model_dump(),
            reasoning=stage1.reasoning,
            route=stage2.route,
            escalation_group=dispatch.escalation_group,
            execution_id=dispatch.execution_id,
            overrides=stage2.overrides_applied,
            stage_timings_ms=timings,
        )

    except Exception:  # noqa: BLE001
        logger.exception("pipeline failure session=%s turn=%s", session_id, session.turn_no)
        bot_message, actions = _safe_fallback()
        _persist_turn(
            db,
            session_id=session_id,
            turn_no=session.turn_no,
            role="bot",
            message=bot_message,
            classification=None,
            actions=actions,
            reasoning="pipeline_exception",
            route="HITL",
            escalation_group="STANDARD",
            execution_id="pipeline_error",
            stage_timings_ms=timings,
        )
        return TurnResult(
            bot_message=bot_message,
            actions=actions,
            classification={"error": "pipeline_exception"},
            reasoning="pipeline_exception",
            route="HITL",
            escalation_group="STANDARD",
            execution_id="pipeline_error",
            overrides=["pipeline_exception"],
            stage_timings_ms=timings,
        )
