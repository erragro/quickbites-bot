"""
Integration tests for chip-tap conversation endpoints:

  GET  /api/chat/starters
  POST /api/sessions/{sid}/select-issue

Runs against the docker-compose Postgres. Uses unique emails so tests
are isolated without per-test rollback.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text as sql_text

from app.auth.routes import limiter
from app.db import SessionLocal
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        limiter.enabled = False
        yield c
        limiter.enabled = True


def _fresh_user(client: TestClient) -> tuple[str, str, str]:
    email = f"chip-{uuid.uuid4().hex[:12]}@example.com"
    r = client.post("/auth/signup", json={"email": email, "password": "password1"})
    assert r.status_code == 201
    body = r.json()
    return email, body["access_token"], body["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _issue_type_id(code: str) -> str:
    """Look up an issue type UUID by its stable seed code."""
    with SessionLocal() as db:
        row = db.execute(
            sql_text("SELECT id FROM issue_types WHERE code = :c"),
            {"c": code},
        ).scalar_one()
        return str(row)


def test_starters_returns_full_tree(client: TestClient):
    _, token, _ = _fresh_user(client)
    r = client.get("/api/chat/starters", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert "business_units" in body
    units = body["business_units"]
    assert len(units) >= 4  # seeded 4 top-level BUs

    codes = {u["code"] for u in units}
    assert {"orders", "delivery", "payments", "account"}.issubset(codes)

    # Every BU has at least one issue type.
    for u in units:
        assert len(u["issue_types"]) >= 1
        for it in u["issue_types"]:
            assert it["code"] and it["name"] and it["id"]


def test_starters_requires_auth(client: TestClient):
    r = client.get("/api/chat/starters")
    assert r.status_code == 401


def test_select_issue_persists_and_renders_ack(client: TestClient):
    _, token, _ = _fresh_user(client)

    # Create a session first — chip select needs an existing session.
    r = client.post("/api/sessions", json={}, headers=_auth(token))
    assert r.status_code == 201
    sid = r.json()["session_id"]

    # missing_item + a real seeded order id (452, Rahul / Express Pizza)
    r = client.post(
        f"/api/sessions/{sid}/select-issue",
        json={
            "issue_type_id": _issue_type_id("missing_item"),
            "order_id": 452,
        },
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Ack text has real content and no leaked template scaffolding.
    ack = body["acknowledgment"]
    assert ack
    assert "{{" not in ack and "}}" not in ack

    # Resolved data points include at least customer + order + restaurant
    # (missing_item declares those three).
    assert set(body["resolved_data_points"]) >= {
        "customer_profile",
        "order_full",
        "restaurant_history",
    }

    # Session detail should now carry the issue type + a bot turn with
    # the ack text.
    detail = client.get(
        f"/api/sessions/{sid}", headers=_auth(token),
    ).json()
    turns = detail["turns"]
    assert any(t["role"] == "bot" and t["message"] == ack for t in turns)


def test_select_issue_without_order_still_returns_ack(client: TestClient):
    """Templates degrade gracefully when order/customer aren't provided —
    the sentence with {{order.id}} gets dropped, but at least one
    sentence should survive."""
    _, token, _ = _fresh_user(client)
    sid = client.post("/api/sessions", json={}, headers=_auth(token)).json()["session_id"]

    r = client.post(
        f"/api/sessions/{sid}/select-issue",
        json={"issue_type_id": _issue_type_id("cold_food")},
        headers=_auth(token),
    )
    assert r.status_code == 200
    body = r.json()
    ack = body["acknowledgment"]
    assert ack.strip()
    assert "{{" not in ack
    # order + restaurant + customer all missing (no order_id, no customer_id)
    assert body["resolved_data_points"] == []


def test_select_issue_404_for_unknown_issue_type(client: TestClient):
    _, token, _ = _fresh_user(client)
    sid = client.post("/api/sessions", json={}, headers=_auth(token)).json()["session_id"]

    r = client.post(
        f"/api/sessions/{sid}/select-issue",
        json={"issue_type_id": str(uuid.uuid4())},
        headers=_auth(token),
    )
    assert r.status_code == 404


def test_select_issue_cross_user_returns_404(client: TestClient):
    """Selecting an issue on someone else's session must 404 (anti-enum)."""
    _, token_a, _ = _fresh_user(client)
    _, token_b, _ = _fresh_user(client)

    sid_a = client.post("/api/sessions", json={}, headers=_auth(token_a)).json()["session_id"]

    r = client.post(
        f"/api/sessions/{sid_a}/select-issue",
        json={"issue_type_id": _issue_type_id("cold_food")},
        headers=_auth(token_b),
    )
    assert r.status_code == 404


def test_select_issue_sets_title_from_issue_name(client: TestClient):
    _, token, _ = _fresh_user(client)
    sid = client.post("/api/sessions", json={}, headers=_auth(token)).json()["session_id"]

    client.post(
        f"/api/sessions/{sid}/select-issue",
        json={"issue_type_id": _issue_type_id("double_charge")},
        headers=_auth(token),
    )
    detail = client.get(f"/api/sessions/{sid}", headers=_auth(token)).json()
    assert detail["title"] == "Charged twice"


def test_select_issue_requires_auth(client: TestClient):
    r = client.post(
        "/api/sessions/anything/select-issue",
        json={"issue_type_id": str(uuid.uuid4())},
    )
    assert r.status_code == 401
