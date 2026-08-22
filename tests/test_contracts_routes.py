"""
/api/contracts HTTP integration tests.

Covers: upload validation (mime, size, empty), list/get ownership (must
be 404 on cross-user access), delete idempotency + file removal.

Storage root is redirected to a fresh tmp dir per module so each run
starts with an empty filesystem.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.auth.routes import limiter
from app.config import settings
from app.contracts import processor as contract_processor, service as contract_service
from app.contracts.storage import LocalStorage
from app.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def storage_root(tmp_path_factory) -> Path:
    """Fresh dir for this test module. Real settings.contract_storage_root
    is left untouched — we inject a LocalStorage directly via
    contract_service._storage."""
    return tmp_path_factory.mktemp("contract-storage")


@pytest.fixture(scope="module")
def client(storage_root, monkeypatch_module):
    with TestClient(app) as c:
        limiter.enabled = False
        # Force the service to use our tmp dir for the lifetime of the module.
        contract_service._storage = LocalStorage(root=storage_root)
        # Stub the background OCR + Stage 1 processor so tests don't hit
        # Gemini. Route-level tests care about validation, ownership, and
        # persistence — the processor is unit-tested separately in
        # tests/test_contracts_processor.py.
        monkeypatch_module.setattr(
            contract_processor, "process_contract_bg", lambda _cid: None,
        )
        yield c
        limiter.enabled = True
        contract_service.reset_storage()


@pytest.fixture(scope="module")
def monkeypatch_module():
    """Module-scoped monkeypatch — pytest's built-in is function-scoped
    which doesn't compose with module-scoped fixtures."""
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    yield mp
    mp.undo()


def _new_user(client: TestClient) -> tuple[str, str]:
    email = f"contracts-{uuid.uuid4().hex[:12]}@example.com"
    r = client.post(
        "/auth/signup",
        json={"email": email, "password": "password1"},
    )
    assert r.status_code == 201, r.text
    return email, r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _pdf_bytes(size: int = 500) -> bytes:
    """Minimal PDF-ish payload. The routes only look at MIME + size, not
    at PDF structure, so this is fine for happy-path validation."""
    header = b"%PDF-1.4\n%dummy\n"
    return header + b"0" * (size - len(header))


# ---------------------------------------------------------------------------
# Upload — happy path + validation errors
# ---------------------------------------------------------------------------


def test_upload_pdf_creates_row_and_file(client: TestClient, storage_root: Path):
    _, token = _new_user(client)
    r = client.post(
        "/api/contracts",
        headers=_auth(token),
        files={"file": ("swiggy_contract.pdf", _pdf_bytes(1024), "application/pdf")},
        data={"target_language": "en"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["filename"] == "swiggy_contract.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["size_bytes"] == 1024
    assert body["status"] == "uploaded"
    contract_id = body["id"]

    # File should be on disk under contracts/{user_id}/{contract_id}.pdf
    hits = list(storage_root.rglob(f"{contract_id}.pdf"))
    assert len(hits) == 1
    assert hits[0].stat().st_size == 1024


def test_upload_rejects_unsupported_mime(client: TestClient):
    _, token = _new_user(client)
    r = client.post(
        "/api/contracts",
        headers=_auth(token),
        files={"file": ("resume.docx", b"fake docx bytes", "application/msword")},
        data={"target_language": "en"},
    )
    assert r.status_code == 415, r.text
    assert "unsupported file type" in r.json()["detail"].lower()


def test_upload_rejects_empty_file(client: TestClient):
    _, token = _new_user(client)
    r = client.post(
        "/api/contracts",
        headers=_auth(token),
        files={"file": ("empty.pdf", b"", "application/pdf")},
        data={"target_language": "en"},
    )
    assert r.status_code == 400
    assert "empty" in r.json()["detail"].lower()


def test_upload_rejects_oversize(client: TestClient, monkeypatch):
    _, token = _new_user(client)
    # Temporarily shrink the ceiling so we don't have to allocate 10MB.
    monkeypatch.setattr(settings, "contract_max_bytes", 1024)
    r = client.post(
        "/api/contracts",
        headers=_auth(token),
        files={"file": ("huge.pdf", _pdf_bytes(2048), "application/pdf")},
        data={"target_language": "en"},
    )
    assert r.status_code == 413
    assert "too large" in r.json()["detail"].lower()


def test_upload_accepts_jpeg(client: TestClient):
    _, token = _new_user(client)
    # JFIF header — enough that some libraries would classify it as JPEG.
    payload = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00" + b"\x00" * 500
    r = client.post(
        "/api/contracts",
        headers=_auth(token),
        files={"file": ("scan.jpg", payload, "image/jpeg")},
        data={"target_language": "en"},
    )
    assert r.status_code == 201


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------


def test_upload_requires_auth(client: TestClient):
    r = client.post(
        "/api/contracts",
        files={"file": ("x.pdf", _pdf_bytes(500), "application/pdf")},
        data={"target_language": "en"},
    )
    assert r.status_code == 401


def test_list_requires_auth(client: TestClient):
    r = client.get("/api/contracts")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# List + get — ownership
# ---------------------------------------------------------------------------


def test_list_returns_only_own_contracts(client: TestClient):
    _, alice = _new_user(client)
    _, bob = _new_user(client)

    # Alice uploads two
    for i in range(2):
        r = client.post(
            "/api/contracts",
            headers=_auth(alice),
            files={"file": (f"a{i}.pdf", _pdf_bytes(400), "application/pdf")},
            data={"target_language": "en"},
        )
        assert r.status_code == 201

    # Bob uploads one
    r = client.post(
        "/api/contracts",
        headers=_auth(bob),
        files={"file": ("b.pdf", _pdf_bytes(400), "application/pdf")},
        data={"target_language": "en"},
    )
    assert r.status_code == 201

    alice_list = client.get("/api/contracts", headers=_auth(alice)).json()
    bob_list = client.get("/api/contracts", headers=_auth(bob)).json()
    assert len(alice_list) == 2
    assert len(bob_list) == 1
    assert {c["filename"] for c in alice_list} == {"a0.pdf", "a1.pdf"}
    assert {c["filename"] for c in bob_list} == {"b.pdf"}


def test_get_cross_user_returns_404_not_403(client: TestClient):
    _, alice = _new_user(client)
    _, bob = _new_user(client)

    r = client.post(
        "/api/contracts",
        headers=_auth(alice),
        files={"file": ("a.pdf", _pdf_bytes(400), "application/pdf")},
        data={"target_language": "en"},
    )
    alice_id = r.json()["id"]

    r = client.get(f"/api/contracts/{alice_id}", headers=_auth(bob))
    # 404 (not 403) so the API doesn't leak contract-id existence.
    assert r.status_code == 404


def test_get_own_contract_returns_detail(client: TestClient):
    _, token = _new_user(client)
    r = client.post(
        "/api/contracts",
        headers=_auth(token),
        files={"file": ("c.pdf", _pdf_bytes(600), "application/pdf")},
        data={"target_language": "en"},
    )
    cid = r.json()["id"]

    r = client.get(f"/api/contracts/{cid}", headers=_auth(token))
    assert r.status_code == 200
    detail = r.json()
    assert detail["id"] == cid
    assert detail["status"] == "uploaded"
    # Detail-only fields present but empty pre-processing.
    assert detail["ocr_text"] is None
    assert detail["stages"] is None


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_removes_row_and_file(
    client: TestClient, storage_root: Path,
):
    _, token = _new_user(client)
    r = client.post(
        "/api/contracts",
        headers=_auth(token),
        files={"file": ("d.pdf", _pdf_bytes(400), "application/pdf")},
        data={"target_language": "en"},
    )
    cid = r.json()["id"]

    files_before = list(storage_root.rglob(f"{cid}.pdf"))
    assert len(files_before) == 1

    r = client.delete(f"/api/contracts/{cid}", headers=_auth(token))
    assert r.status_code == 204

    # File gone
    files_after = list(storage_root.rglob(f"{cid}.pdf"))
    assert files_after == []

    # Row gone
    r = client.get(f"/api/contracts/{cid}", headers=_auth(token))
    assert r.status_code == 404


def test_delete_cross_user_returns_404(client: TestClient):
    _, alice = _new_user(client)
    _, bob = _new_user(client)

    r = client.post(
        "/api/contracts",
        headers=_auth(alice),
        files={"file": ("secret.pdf", _pdf_bytes(400), "application/pdf")},
        data={"target_language": "en"},
    )
    cid = r.json()["id"]

    r = client.delete(f"/api/contracts/{cid}", headers=_auth(bob))
    assert r.status_code == 404

    # Alice's file still there.
    r = client.get(f"/api/contracts/{cid}", headers=_auth(alice))
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Filename sanitisation
# ---------------------------------------------------------------------------


def test_upload_sanitises_path_traversal_filename(client: TestClient):
    _, token = _new_user(client)
    r = client.post(
        "/api/contracts",
        headers=_auth(token),
        files={
            "file": (
                "../../etc/passwd.pdf",
                _pdf_bytes(400),
                "application/pdf",
            )
        },
        data={"target_language": "en"},
    )
    assert r.status_code == 201
    # Slashes replaced with underscores in the display filename.
    assert "/" not in r.json()["filename"]
    assert r.json()["filename"] == ".._.._etc_passwd.pdf"
