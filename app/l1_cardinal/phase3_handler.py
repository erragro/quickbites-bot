"""
Phase 3 Handler — session state management. Loads (or creates) the session row,
rehydrates the conversation history from the turns table. No source-verification
HMAC is needed here (unlike kirana_kart) because the 'source' is our own runner
calling out to the simulator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class HistoryTurn:
    turn_no: int
    role: str
    message: str
    actions: list[dict] = field(default_factory=list)


@dataclass
class SessionState:
    session_id: str
    simulator_session_id: Optional[str]
    mode: str
    scenario_id: Optional[int]
    max_turns: Optional[int]
    known_order_id: Optional[int]
    known_customer_id: Optional[int]
    history: list[HistoryTurn]
    turn_no: int

    @property
    def prior_bot_actions(self) -> list[dict]:
        """Flat list of every action emitted in prior bot turns, oldest first."""
        out: list[dict] = []
        for t in self.history:
            if t.role == "bot" and t.actions:
                out.extend(t.actions)
        return out

    @property
    def already_escalated(self) -> bool:
        return any(a.get("type") == "escalate_to_human" for a in self.prior_bot_actions)

    @property
    def already_flag_abused(self) -> bool:
        return any(a.get("type") == "flag_abuse" for a in self.prior_bot_actions)

    @property
    def prior_bot_message(self) -> Optional[str]:
        for t in reversed(self.history):
            if t.role == "bot":
                return t.message
        return None


def load_or_create(
    db: Session,
    *,
    session_id: str,
    simulator_session_id: str | None = None,
    mode: str = "dev",
    scenario_id: int | None = None,
    max_turns: int | None = None,
) -> SessionState:
    row = db.execute(
        text("SELECT * FROM sessions WHERE session_id = :sid"),
        {"sid": session_id},
    ).first()

    if not row:
        db.execute(
            text(
                """
                INSERT INTO sessions (
                    session_id, simulator_session_id, mode, scenario_id, max_turns
                ) VALUES (:sid, :ssid, :mode, :scenario, :max_turns)
                """
            ),
            {
                "sid": session_id,
                "ssid": simulator_session_id,
                "mode": mode,
                "scenario": scenario_id,
                "max_turns": max_turns,
            },
        )
        db.commit()
        row = db.execute(
            text("SELECT * FROM sessions WHERE session_id = :sid"),
            {"sid": session_id},
        ).first()

    history_rows = db.execute(
        text(
            "SELECT turn_no, role, message, actions FROM turns "
            "WHERE session_id = :sid ORDER BY turn_no ASC, "
            "CASE role WHEN 'customer' THEN 0 ELSE 1 END ASC"
        ),
        {"sid": session_id},
    ).all()
    history = []
    for r in history_rows:
        acts: list[dict] = []
        raw = r.actions
        if raw:
            try:
                acts = json.loads(raw) if isinstance(raw, str) else list(raw)
            except (json.JSONDecodeError, TypeError):
                acts = []
        history.append(
            HistoryTurn(
                turn_no=r.turn_no,
                role=r.role,
                message=r.message or "",
                actions=acts,
            )
        )
    turn_no = (history[-1].turn_no + 1) if history else 1

    return SessionState(
        session_id=row.session_id,
        simulator_session_id=row.simulator_session_id,
        mode=row.mode,
        scenario_id=row.scenario_id,
        max_turns=row.max_turns,
        known_order_id=row.known_order_id,
        known_customer_id=row.known_customer_id,
        history=history,
        turn_no=turn_no,
    )


def update_known_ids(
    db: Session,
    session_id: str,
    *,
    order_id: int | None = None,
    customer_id: int | None = None,
) -> None:
    sets = []
    params: dict = {"sid": session_id}
    if order_id is not None:
        sets.append("known_order_id = :oid")
        params["oid"] = order_id
    if customer_id is not None:
        sets.append("known_customer_id = :cid")
        params["cid"] = customer_id
    if not sets:
        return
    db.execute(
        text(f"UPDATE sessions SET {', '.join(sets)} WHERE session_id = :sid"),
        params,
    )
    db.commit()


def close_session(
    db: Session,
    session_id: str,
    *,
    close_reason: str,
    final_score: dict | None = None,
) -> None:
    db.execute(
        text(
            """
            UPDATE sessions
            SET closed_at = now(), close_reason = :reason, final_score = :score
            WHERE session_id = :sid
            """
        ),
        {
            "sid": session_id,
            "reason": close_reason,
            "score": None if final_score is None else _jsonify(final_score),
        },
    )
    db.commit()


def _jsonify(obj: dict) -> str:
    import json

    return json.dumps(obj)
