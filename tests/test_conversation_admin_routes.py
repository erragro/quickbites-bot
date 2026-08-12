"""
/api/admin/conversation/* CRUD tests.

Uses the same fresh-user pattern as the other route tests; the first
signup in the test DB becomes super_admin (via the bootstrap rule) so
those tests can immediately hit the admin surface.

Uses unique BU / issue-type codes per test so multiple runs don't
collide with each other in the persistent Postgres.
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
def admin_token():
    """Yields a super_admin token, promoting whoever exists to super
    admin if necessary. Simpler than the first-user-wins path — tests
    already share a DB with earlier fixtures."""
    email = f"convadmin-{uuid.uuid4().hex[:12]}@example.com"
    with TestClient(app) as c:
        limiter.enabled = False
        r = c.post("/auth/signup", json={"email": email, "password": "password1"})
        assert r.status_code == 201, r.text
        token = r.json()["access_token"]
        # Explicit promote via SQL — earlier bootstrap logic only auto-
        # promotes the very first user in the DB.
        with SessionLocal() as db:
            db.execute(
                sql_text("UPDATE users SET is_super_admin = true WHERE email = :e"),
                {"e": email},
            )
            db.commit()
        yield token
        limiter.enabled = True


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        limiter.enabled = False
        yield c
        limiter.enabled = True


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _u(prefix: str) -> str:
    """Unique short slug for a test-run entity code."""
    return f"{prefix}-{uuid.uuid4().hex[:6]}"


# ---------- Business Units ----------


def test_list_business_units_returns_seeded_rows(client, admin_token):
    r = client.get(
        "/api/admin/conversation/business-units", headers=_auth(admin_token),
    )
    assert r.status_code == 200
    codes = {b["code"] for b in r.json()}
    assert {"orders", "delivery", "payments", "account"}.issubset(codes)


def test_business_unit_crud_roundtrip(client, admin_token):
    code = _u("test_bu")
    # Create
    r = client.post(
        "/api/admin/conversation/business-units",
        headers=_auth(admin_token),
        json={"code": code, "name": "Test BU", "icon": "Boxes", "sort_order": 500},
    )
    assert r.status_code == 201, r.text
    bu = r.json()
    bu_id = bu["id"]
    assert bu["code"] == code

    # Update
    r = client.patch(
        f"/api/admin/conversation/business-units/{bu_id}",
        headers=_auth(admin_token),
        json={"name": "Test BU renamed"},
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Test BU renamed"

    # Delete
    r = client.delete(
        f"/api/admin/conversation/business-units/{bu_id}",
        headers=_auth(admin_token),
    )
    assert r.status_code == 204


def test_delete_business_unit_with_children_rejected(client, admin_token):
    # Orders BU has seeded issue types → delete must 409.
    r = client.get(
        "/api/admin/conversation/business-units", headers=_auth(admin_token),
    )
    orders = next(b for b in r.json() if b["code"] == "orders")
    r = client.delete(
        f"/api/admin/conversation/business-units/{orders['id']}",
        headers=_auth(admin_token),
    )
    assert r.status_code == 409
    assert "issue types" in r.json()["detail"].lower()


def test_business_unit_code_uniqueness(client, admin_token):
    code = _u("dupe")
    client.post(
        "/api/admin/conversation/business-units",
        headers=_auth(admin_token),
        json={"code": code, "name": "Dupe 1"},
    )
    r = client.post(
        "/api/admin/conversation/business-units",
        headers=_auth(admin_token),
        json={"code": code, "name": "Dupe 2"},
    )
    assert r.status_code == 409


def test_bu_endpoints_reject_non_admin(client):
    """A regular user must not be able to hit any BU endpoint."""
    email = f"regular-{uuid.uuid4().hex[:12]}@example.com"
    r = client.post("/auth/signup", json={"email": email, "password": "password1"})
    token = r.json()["access_token"]
    r = client.get(
        "/api/admin/conversation/business-units",
        headers=_auth(token),
    )
    assert r.status_code == 403


# ---------- Issue Types ----------


def test_issue_type_crud_and_binding(client, admin_token):
    # Pick an existing BU to hang the issue type off.
    bus = client.get(
        "/api/admin/conversation/business-units", headers=_auth(admin_token),
    ).json()
    bu_id = next(b["id"] for b in bus if b["code"] == "account")

    code = _u("test_it")
    r = client.post(
        "/api/admin/conversation/issue-types",
        headers=_auth(admin_token),
        json={
            "business_unit_id": bu_id,
            "code": code,
            "name": "Test issue",
            "description": "a description",
            "icon": "HelpCircle",
            "routes_to_intent": "other",
            "sort_order": 999,
        },
    )
    assert r.status_code == 201, r.text
    it = r.json()
    it_id = it["id"]

    # Bind two data points.
    dps = client.get(
        "/api/admin/conversation/data-points", headers=_auth(admin_token),
    ).json()
    dp_ids = [d["id"] for d in dps[:2]]

    r = client.put(
        f"/api/admin/conversation/issue-types/{it_id}/data-points",
        headers=_auth(admin_token),
        json={
            "bindings": [
                {"data_point_id": dp_ids[0], "is_required": True, "sort_order": 10},
                {"data_point_id": dp_ids[1], "is_required": False, "sort_order": 20},
            ]
        },
    )
    assert r.status_code == 200
    it_after = r.json()
    assert len(it_after["data_points"]) == 2

    # Reject unknown data-point ids.
    r = client.put(
        f"/api/admin/conversation/issue-types/{it_id}/data-points",
        headers=_auth(admin_token),
        json={"bindings": [{"data_point_id": str(uuid.uuid4()), "is_required": True, "sort_order": 10}]},
    )
    assert r.status_code == 400

    # Delete cleanup
    r = client.delete(
        f"/api/admin/conversation/issue-types/{it_id}",
        headers=_auth(admin_token),
    )
    assert r.status_code == 204


def test_issue_type_rejects_invalid_intent(client, admin_token):
    bus = client.get(
        "/api/admin/conversation/business-units", headers=_auth(admin_token),
    ).json()
    bu_id = bus[0]["id"]
    r = client.post(
        "/api/admin/conversation/issue-types",
        headers=_auth(admin_token),
        json={
            "business_unit_id": bu_id,
            "code": _u("bad_intent"),
            "name": "Bad intent",
            "routes_to_intent": "not_a_real_intent",
        },
    )
    assert r.status_code == 400


def test_issue_type_accepts_null_intent(client, admin_token):
    """routes_to_intent is optional — issue type can exist without a
    matrix binding (falls through to Stage 2's safety net at runtime)."""
    bus = client.get(
        "/api/admin/conversation/business-units", headers=_auth(admin_token),
    ).json()
    bu_id = bus[0]["id"]
    r = client.post(
        "/api/admin/conversation/issue-types",
        headers=_auth(admin_token),
        json={
            "business_unit_id": bu_id,
            "code": _u("no_intent"),
            "name": "No intent",
        },
    )
    assert r.status_code == 201
    assert r.json()["routes_to_intent"] is None


# ---------- Templates ----------


def test_template_crud_for_issue_type(client, admin_token):
    # Grab any seeded issue type.
    its = client.get(
        "/api/admin/conversation/issue-types", headers=_auth(admin_token),
    ).json()
    it = next(x for x in its if x["code"] == "cold_food")

    r = client.post(
        f"/api/admin/conversation/issue-types/{it['id']}/templates",
        headers=_auth(admin_token),
        json={"template": "Custom ack — {{customer.first_name}}", "weight": 3},
    )
    assert r.status_code == 201
    tpl_id = r.json()["id"]

    r = client.patch(
        f"/api/admin/conversation/templates/{tpl_id}",
        headers=_auth(admin_token),
        json={"weight": 1, "is_active": False},
    )
    assert r.status_code == 200
    assert r.json()["weight"] == 1
    assert r.json()["is_active"] is False

    r = client.delete(
        f"/api/admin/conversation/templates/{tpl_id}",
        headers=_auth(admin_token),
    )
    assert r.status_code == 204


def test_data_points_are_read_only(client, admin_token):
    """No POST on /data-points — registry is code, not admin-editable."""
    r = client.post(
        "/api/admin/conversation/data-points",
        headers=_auth(admin_token),
        json={},
    )
    assert r.status_code == 405
