from __future__ import annotations

import logging
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app import simulator_client
from app.db import db_session, engine
from app.migrations import bootstrap
from app.runners import dev_runner, prod_runner
from app.runners.session_runner import SessionSummary


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="QuickBites Support Bot",
    version="0.1.0",
    description="Cardinal-inspired synchronous 5-phase + 4-stage LLM pipeline.",
)


@app.on_event("startup")
def _startup() -> None:
    try:
        loaded = bootstrap.run()
        logger.info("bootstrap %s", loaded)
    except Exception:
        logger.exception("bootstrap failed — service will serve /healthz but runs will error")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


class RunDevBody(BaseModel):
    scenario_id: Optional[int] = None


@app.post("/run/dev")
def run_dev(body: RunDevBody) -> SessionSummary:
    if body.scenario_id is not None and body.scenario_id not in (101, 102, 103, 104, 105):
        raise HTTPException(400, "scenario_id must be 101-105 or omitted")
    return dev_runner.run_dev(body.scenario_id)


@app.post("/run/dev/all")
def run_dev_all() -> list[SessionSummary]:
    return dev_runner.run_all_rehearsal()


@app.post("/run/prod")
def run_prod() -> dict:
    results = prod_runner.run_prod_all()
    return {
        "sessions_run": len(results),
        "summaries": [s for s in results],
    }


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    with db_session() as db:
        s = db.execute(
            text("SELECT * FROM sessions WHERE session_id = :sid"),
            {"sid": session_id},
        ).first()
        if not s:
            raise HTTPException(404, "session not found")
        turns = [
            dict(r._mapping)
            for r in db.execute(
                text(
                    """
                    SELECT turn_no, role, message, classification, actions, reasoning,
                           route, escalation_group, execution_id, stage_timings_ms, created_at
                    FROM turns WHERE session_id = :sid
                    ORDER BY id ASC
                    """
                ),
                {"sid": session_id},
            )
        ]
    session_row = dict(s._mapping)
    return {"session": session_row, "turns": turns}


@app.get("/sessions")
def list_sessions(limit: int = 50) -> list[dict]:
    with db_session() as db:
        rows = db.execute(
            text(
                "SELECT session_id, mode, scenario_id, opened_at, closed_at, close_reason "
                "FROM sessions ORDER BY opened_at DESC LIMIT :lim"
            ),
            {"lim": limit},
        ).all()
    return [dict(r._mapping) for r in rows]


@app.get("/score")
def score() -> dict:
    return simulator_client.candidate_summary()


@app.get("/simulator/healthz")
def simulator_healthz() -> dict:
    return simulator_client.healthz()
