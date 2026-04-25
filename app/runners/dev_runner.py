from __future__ import annotations

import logging

from app.runners.session_runner import SessionSummary, run_one_session


logger = logging.getLogger(__name__)


def run_dev(scenario_id: int | None = None) -> SessionSummary:
    return run_one_session(mode="dev", scenario_id=scenario_id)


def run_all_rehearsal() -> list[SessionSummary]:
    results: list[SessionSummary] = []
    for sid in (101, 102, 103, 104, 105):
        try:
            results.append(run_dev(sid))
        except Exception:  # noqa: BLE001
            logger.exception("dev scenario %s failed", sid)
    return results
