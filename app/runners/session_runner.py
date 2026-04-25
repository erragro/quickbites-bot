"""
Generic session runner. Given a mode (+ optional scenario_id) it:
  1. POSTs /v1/session/start
  2. Loops: pipeline.run_turn → POST /v1/session/{id}/reply → feed next
  3. Stops when `done` or our own pipeline emits a `close` action
  4. Closes the sessions row

Shared by both dev and prod runners; prod_runner calls this in a loop until
the simulator returns 409.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from app import simulator_client
from app.db import db_session
from app.l1_cardinal import phase3_handler
from app.l1_cardinal.pipeline import TurnResult, run_turn


logger = logging.getLogger(__name__)


@dataclass
class SessionSummary:
    session_id: str
    simulator_session_id: str
    scenario_id: int
    mode: str
    turns: list[dict] = field(default_factory=list)
    close_reason: str | None = None
    score: dict | None = None


def _contains_close_action(actions: list[dict]) -> bool:
    return any(a.get("type") == "close" for a in actions)


def run_one_session(
    mode: str = "dev",
    scenario_id: int | None = None,
) -> SessionSummary:
    start = simulator_client.start_session(mode=mode, scenario_id=scenario_id)
    sim_session = start["session_id"]
    our_session = uuid.uuid4().hex[:16]

    summary = SessionSummary(
        session_id=our_session,
        simulator_session_id=sim_session,
        scenario_id=start.get("scenario_id"),
        mode=start.get("mode", mode),
    )

    # First customer_message comes from /start
    customer_message = start["customer_message"]
    max_turns = start.get("max_turns")

    done = False
    close_reason = None
    score = None

    while customer_message and not done:
        with db_session() as db:
            tr: TurnResult = run_turn(
                db,
                session_id=our_session,
                customer_message=customer_message,
                simulator_session_id=sim_session,
                mode=mode,
                scenario_id=start.get("scenario_id"),
                max_turns=max_turns,
            )

        summary.turns.append(
            {
                "customer_message": customer_message,
                "bot_message": tr.bot_message,
                "actions": tr.actions,
                "classification": tr.classification,
                "reasoning": tr.reasoning,
                "route": tr.route,
                "escalation_group": tr.escalation_group,
                "execution_id": tr.execution_id,
                "overrides": tr.overrides,
                "stage_timings_ms": tr.stage_timings_ms,
            }
        )

        try:
            sim_resp = simulator_client.reply(
                sim_session, tr.bot_message, tr.actions
            )
        except Exception:  # noqa: BLE001
            logger.exception("simulator reply failed session=%s", sim_session)
            break

        done = bool(sim_resp.get("done")) or _contains_close_action(tr.actions)
        close_reason = sim_resp.get("close_reason")
        score = sim_resp.get("score")
        customer_message = sim_resp.get("customer_message")

    summary.close_reason = close_reason
    summary.score = score

    with db_session() as db:
        phase3_handler.close_session(
            db,
            our_session,
            close_reason=close_reason or "ended",
            final_score=score,
        )

    return summary
