from __future__ import annotations

import logging

from app import simulator_client
from app.runners.session_runner import SessionSummary, run_one_session


logger = logging.getLogger(__name__)


def run_prod_all(max_sessions: int = 44) -> list[SessionSummary]:
    """Run prod scenarios until the simulator returns 409 (all 22 done) or we
    hit the safety cap. 44 is the token rate limit per SIMULATOR_API.md."""
    results: list[SessionSummary] = []
    for _ in range(max_sessions):
        try:
            summary = run_one_session(mode="prod", scenario_id=None)
        except simulator_client.SimulatorError as exc:
            if exc.status == 409:
                logger.info("prod eval set complete")
                break
            logger.exception("prod session failed: %s", exc)
            break
        results.append(summary)
    return results
