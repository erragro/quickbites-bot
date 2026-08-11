"""
/api/sessions HTTP integration tests.

Ownership tests are the security-critical ones: a cross-user access must
return 404 (never 403), and every mutation must require auth.

/chat endpoint is not exercised here — it triggers the LLM pipeline which
needs real API credentials. Covered separately by a live smoke test.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth.routes import limiter
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        limiter.enabled = False
        yield c
        limiter.enabled = True


def _new_user(client: TestClient) -> tuple[str, str]:
    """Returns (email, access_token)."""
    email = f"sessions-{uuid.uuid4().hex[:12]}@example.com"
    r = client.post("/auth/signup", json={"email": email, "password": "password1"})
    assert r.status_code == 201, r.text
    return email, r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_list_sessions_empty_for_new_user(client: TestClient):
    _, token = _new_user(client)
    r = client.get("/api/sessions", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == []


def test_create_lists_get_rename_delete_roundtrip(client: TestClient):
    _, token = _new_user(client)

    # Create
    r = client.post("/api/sessions", json={"title": "First chat"}, headers=_auth(token))
    assert r.status_code == 201
    session = r.json()
    sid = session["session_id"]
    assert session["title"] == "First chat"

    # List — should include the new one
    r = client.get("/api/sessions", headers=_auth(token))
    assert r.status_code == 200
    ids = [s["session_id"] for s in r.json()]
    assert sid in ids

    # Get detail — turns empty since no messages sent
    r = client.get(f"/api/sessions/{sid}", headers=_auth(token))
    assert r.status_code == 200
    detail = r.json()
    assert detail["session_id"] == sid
    assert detail["turns"] == []

    # Rename
    r = client.patch(
        f"/api/sessions/{sid}",
        json={"title": "Renamed"},
        headers=_auth(token),
    )
    assert r.status_code == 200
    assert r.json()["title"] == "Renamed"

    # Delete
    r = client.delete(f"/api/sessions/{sid}", headers=_auth(token))
    assert r.status_code == 204

    # 404 after delete
    r = client.get(f"/api/sessions/{sid}", headers=_auth(token))
    assert r.status_code == 404


def test_all_routes_reject_unauthenticated(client: TestClient):
    for method, url in [
        ("get", "/api/sessions"),
        ("post", "/api/sessions"),
        ("get", "/api/sessions/anything"),
        ("patch", "/api/sessions/anything"),
        ("delete", "/api/sessions/anything"),
    ]:
        # None of these should be reachable without a token.
        r = client.request(method, url)
        assert r.status_code == 401, f"{method} {url}: {r.status_code}"


def test_cross_user_access_returns_404_not_403(client: TestClient):
    """
    Anti-enumeration: user A's session must not tell user B whether it
    exists. 403 would leak that; 404 does not.
    """
    _, token_a = _new_user(client)
    _, token_b = _new_user(client)

    create = client.post(
        "/api/sessions", json={"title": "A's chat"}, headers=_auth(token_a),
    )
    sid_a = create.json()["session_id"]

    # User B tries every endpoint against A's session.
    r = client.get(f"/api/sessions/{sid_a}", headers=_auth(token_b))
    assert r.status_code == 404

    r = client.patch(
        f"/api/sessions/{sid_a}", json={"title": "hack"}, headers=_auth(token_b),
    )
    assert r.status_code == 404

    r = client.delete(f"/api/sessions/{sid_a}", headers=_auth(token_b))
    assert r.status_code == 404

    # User A can still see + modify their own.
    r = client.get(f"/api/sessions/{sid_a}", headers=_auth(token_a))
    assert r.status_code == 200


def test_list_scoped_to_owner(client: TestClient):
    _, token_a = _new_user(client)
    _, token_b = _new_user(client)

    client.post("/api/sessions", json={"title": "A1"}, headers=_auth(token_a))
    client.post("/api/sessions", json={"title": "A2"}, headers=_auth(token_a))
    client.post("/api/sessions", json={"title": "B1"}, headers=_auth(token_b))

    a_sessions = client.get("/api/sessions", headers=_auth(token_a)).json()
    b_sessions = client.get("/api/sessions", headers=_auth(token_b)).json()

    a_titles = {s["title"] for s in a_sessions}
    b_titles = {s["title"] for s in b_sessions}

    assert "A1" in a_titles and "A2" in a_titles and "B1" not in a_titles
    assert "B1" in b_titles and "A1" not in b_titles and "A2" not in b_titles


def test_rename_requires_non_empty_title(client: TestClient):
    _, token = _new_user(client)
    create = client.post("/api/sessions", json={}, headers=_auth(token))
    sid = create.json()["session_id"]

    r = client.patch(
        f"/api/sessions/{sid}", json={"title": ""}, headers=_auth(token),
    )
    assert r.status_code == 422


def test_pagination_bounds(client: TestClient):
    _, token = _new_user(client)
    r = client.get("/api/sessions?limit=0", headers=_auth(token))
    assert r.status_code == 400
    r = client.get("/api/sessions?limit=500", headers=_auth(token))
    assert r.status_code == 400
    r = client.get("/api/sessions?offset=-1", headers=_auth(token))
    assert r.status_code == 400


def test_run_dev_requires_auth(client: TestClient):
    r = client.post("/run/dev", json={"scenario_id": 101})
    assert r.status_code == 401


def test_run_prod_requires_auth(client: TestClient):
    r = client.post("/run/prod")
    assert r.status_code == 401
