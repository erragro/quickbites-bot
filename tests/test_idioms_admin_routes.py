"""
/api/admin/idioms HTTP integration tests.

Covers CRUD happy paths, translation upsert/delete, super-admin
gating, unique-constraint conflicts, and cache invalidation (write
endpoints should force the Aho-Corasick automaton to reload).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth.routes import limiter
from app.main import app
from app.translate import idioms as idiom_runtime


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        limiter.enabled = False
        yield c
        limiter.enabled = True


def _new_user(client: TestClient, *, super_admin: bool = False) -> tuple[str, str]:
    email = f"idmadmin-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/auth/signup", json={"email": email, "password": "password1"})
    assert r.status_code == 201, r.text
    token = r.json()["access_token"]
    if super_admin:
        # First user in a fresh DB is auto super_admin; later users
        # need to be elevated directly. For this test suite the seeds
        # from earlier migrations mean the current signup won't be
        # super_admin unless we bump them explicitly.
        from app.db import db_session
        from app.models import User
        from sqlalchemy import select, update
        with db_session() as db:
            db.execute(
                update(User).where(User.email == email).values(is_super_admin=True)
            )
    return email, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Gating
# ---------------------------------------------------------------------------


def test_list_requires_super_admin(client: TestClient):
    _, regular = _new_user(client)
    r = client.get("/api/admin/idioms", headers=_auth(regular))
    assert r.status_code == 403


def test_create_requires_super_admin(client: TestClient):
    _, regular = _new_user(client)
    r = client.post(
        "/api/admin/idioms",
        headers=_auth(regular),
        json={"source_phrase": "raining cats and dogs", "meaning": "heavy rain", "category": "general"},
    )
    assert r.status_code == 403


# ---------------------------------------------------------------------------
# CRUD happy path
# ---------------------------------------------------------------------------


def test_list_returns_seeded_idioms(client: TestClient):
    _, admin = _new_user(client, super_admin=True)
    r = client.get("/api/admin/idioms", headers=_auth(admin))
    assert r.status_code == 200
    data = r.json()
    # Migration 007 seeds 25 idioms; new admin tests may add more, so
    # assert >= not exact. Every row has a translations array.
    assert len(data) >= 25
    assert all("translations" in row for row in data)
    # Every row has category from our whitelist.
    assert all(row["category"] in {"legal", "work", "money", "general", "safety"} for row in data)


def test_create_then_get_roundtrip(client: TestClient):
    _, admin = _new_user(client, super_admin=True)
    phrase = f"burn the midnight oil {uuid.uuid4().hex[:6]}"
    r = client.post(
        "/api/admin/idioms",
        headers=_auth(admin),
        json={
            "source_phrase": phrase,
            "meaning": "Work very late into the night.",
            "category": "work",
            "translations": [
                {"language": "hi", "translation": "देर रात तक काम करना"},
                {"language": "bn", "translation": "গভীর রাত পর্যন্ত কাজ করা"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_phrase"] == phrase
    assert body["category"] == "work"
    assert body["is_active"] is True
    assert len(body["translations"]) == 2
    langs = {t["language"] for t in body["translations"]}
    assert langs == {"hi", "bn"}

    # Get it back
    r = client.get(f"/api/admin/idioms/{body['id']}", headers=_auth(admin))
    assert r.status_code == 200
    assert r.json()["source_phrase"] == phrase


def test_create_rejects_duplicate_phrase(client: TestClient):
    _, admin = _new_user(client, super_admin=True)
    r = client.post(
        "/api/admin/idioms",
        headers=_auth(admin),
        json={"source_phrase": "in good faith", "meaning": "act honestly", "category": "legal"},
    )
    # Seeded phrase — should conflict.
    assert r.status_code == 409


def test_create_rejects_bad_category(client: TestClient):
    _, admin = _new_user(client, super_admin=True)
    r = client.post(
        "/api/admin/idioms",
        headers=_auth(admin),
        json={"source_phrase": "unique test 1", "meaning": "test", "category": "unknown-cat"},
    )
    assert r.status_code == 422  # Pydantic rejects before hitting DB


def test_patch_updates_fields(client: TestClient):
    _, admin = _new_user(client, super_admin=True)
    phrase = f"early bird {uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/admin/idioms",
        headers=_auth(admin),
        json={"source_phrase": phrase, "meaning": "someone who wakes up early", "category": "general"},
    ).json()

    r = client.patch(
        f"/api/admin/idioms/{created['id']}",
        headers=_auth(admin),
        json={"meaning": "updated meaning", "is_active": False},
    )
    assert r.status_code == 200
    updated = r.json()
    assert updated["meaning"] == "updated meaning"
    assert updated["is_active"] is False
    # Fields we didn't touch stayed put.
    assert updated["source_phrase"] == phrase


def test_delete_removes_idiom_and_translations(client: TestClient):
    _, admin = _new_user(client, super_admin=True)
    phrase = f"cold shoulder {uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/admin/idioms",
        headers=_auth(admin),
        json={
            "source_phrase": phrase,
            "meaning": "deliberately ignore someone",
            "category": "general",
            "translations": [{"language": "hi", "translation": "अनदेखी करना"}],
        },
    ).json()
    cid = created["id"]

    r = client.delete(f"/api/admin/idioms/{cid}", headers=_auth(admin))
    assert r.status_code == 204

    r = client.get(f"/api/admin/idioms/{cid}", headers=_auth(admin))
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Translation endpoints
# ---------------------------------------------------------------------------


def test_upsert_translation_inserts_and_updates(client: TestClient):
    _, admin = _new_user(client, super_admin=True)
    phrase = f"cutting edge {uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/admin/idioms",
        headers=_auth(admin),
        json={"source_phrase": phrase, "meaning": "most advanced", "category": "general"},
    ).json()
    cid = created["id"]

    # Insert a Hindi translation.
    r = client.put(
        f"/api/admin/idioms/{cid}/translations/hi",
        headers=_auth(admin),
        json={"language": "hi", "translation": "अत्याधुनिक", "notes": "modern"},
    )
    assert r.status_code == 200
    row = r.json()
    hi_translations = [t for t in row["translations"] if t["language"] == "hi"]
    assert len(hi_translations) == 1
    assert hi_translations[0]["translation"] == "अत्याधुनिक"

    # Update the same language — should overwrite, not add a second row.
    r = client.put(
        f"/api/admin/idioms/{cid}/translations/hi",
        headers=_auth(admin),
        json={"language": "hi", "translation": "नवीनतम"},
    )
    assert r.status_code == 200
    hi_translations = [t for t in r.json()["translations"] if t["language"] == "hi"]
    assert len(hi_translations) == 1
    assert hi_translations[0]["translation"] == "नवीनतम"


def test_upsert_rejects_path_body_language_mismatch(client: TestClient):
    _, admin = _new_user(client, super_admin=True)
    phrase = f"tip of the iceberg {uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/admin/idioms",
        headers=_auth(admin),
        json={"source_phrase": phrase, "meaning": "just the visible part", "category": "general"},
    ).json()

    r = client.put(
        f"/api/admin/idioms/{created['id']}/translations/hi",
        headers=_auth(admin),
        # Body says bn but path says hi — must reject rather than silently
        # write to the wrong row.
        json={"language": "bn", "translation": "..."},
    )
    assert r.status_code == 400


def test_delete_translation_removes_only_that_language(client: TestClient):
    _, admin = _new_user(client, super_admin=True)
    phrase = f"piece of cake {uuid.uuid4().hex[:6]}"
    created = client.post(
        "/api/admin/idioms",
        headers=_auth(admin),
        json={
            "source_phrase": phrase,
            "meaning": "very easy",
            "category": "general",
            "translations": [
                {"language": "hi", "translation": "आसान काम"},
                {"language": "bn", "translation": "সহজ কাজ"},
            ],
        },
    ).json()
    cid = created["id"]

    r = client.delete(
        f"/api/admin/idioms/{cid}/translations/hi",
        headers=_auth(admin),
    )
    assert r.status_code == 204

    idiom = client.get(f"/api/admin/idioms/{cid}", headers=_auth(admin)).json()
    langs = {t["language"] for t in idiom["translations"]}
    assert langs == {"bn"}


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------


def test_creating_idiom_invalidates_runtime_cache(client: TestClient):
    _, admin = _new_user(client, super_admin=True)
    # Prime the runtime cache.
    idiom_runtime.substitute("act in good faith", target_language="hi")
    assert idiom_runtime._cache is not None

    r = client.post(
        "/api/admin/idioms",
        headers=_auth(admin),
        json={
            "source_phrase": f"once in a blue moon {uuid.uuid4().hex[:6]}",
            "meaning": "very rarely",
            "category": "general",
        },
    )
    assert r.status_code == 201

    # Write endpoint should have reset the cache; next scan rebuilds.
    assert idiom_runtime._cache is None
