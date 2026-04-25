"""
httpx client for the QuickBites simulator. Thin wrapper around the 5 endpoints
we care about. Timeouts default to 30s — the simulator is remote and we'd
rather fail loudly than hang a session.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from app.config import settings


class SimulatorError(RuntimeError):
    def __init__(self, status: int, body: Any) -> None:
        super().__init__(f"simulator_error status={status} body={body}")
        self.status = status
        self.body = body


def _headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "X-Candidate-Token": settings.candidate_token,
    }


def _client() -> httpx.Client:
    return httpx.Client(base_url=settings.simulator_base_url, timeout=30.0)


def start_session(mode: str = "dev", scenario_id: Optional[int] = None) -> dict:
    body: dict[str, Any] = {"mode": mode}
    if scenario_id is not None:
        body["scenario_id"] = scenario_id
    with _client() as c:
        r = c.post("/v1/session/start", json=body, headers=_headers())
    if r.status_code >= 400:
        raise SimulatorError(r.status_code, _safe_body(r))
    return r.json()


def reply(session_id: str, bot_message: str, actions: list[dict]) -> dict:
    body = {"bot_message": bot_message, "actions": actions}
    with _client() as c:
        r = c.post(f"/v1/session/{session_id}/reply", json=body, headers=_headers())
    if r.status_code >= 400:
        raise SimulatorError(r.status_code, _safe_body(r))
    return r.json()


def transcript(session_id: str) -> dict:
    with _client() as c:
        r = c.get(f"/v1/session/{session_id}/transcript", headers=_headers())
    if r.status_code >= 400:
        raise SimulatorError(r.status_code, _safe_body(r))
    return r.json()


def candidate_summary() -> dict:
    with _client() as c:
        r = c.get("/v1/candidate/summary", headers=_headers())
    if r.status_code >= 400:
        raise SimulatorError(r.status_code, _safe_body(r))
    return r.json()


def healthz() -> dict:
    with _client() as c:
        r = c.get("/healthz")
    return {"status": r.status_code, "body": _safe_body(r)}


def _safe_body(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return r.text
