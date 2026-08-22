"""Business logic for the Contract Reader upload surface.

The service owns three things:
  1. Validation — mime, size, filename sanity.
  2. Persistence — write file to storage, insert DB row.
  3. Ownership resolution — every read/write is scoped to (user, contract_id).

Stage-5+ (OCR + three-stage LLM) hangs off the contract row's status
machine ('uploaded' → 'ocr_pending' → ... → 'ready'/'failed'). Those
stages live in separate modules that read from + write back to the row;
this service handles only the upload transaction.
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.contracts.storage import Storage, build_key, make_storage
from app.models import UploadedContract, User


# ---------------------------------------------------------------------------
# Validation constants
# ---------------------------------------------------------------------------

# MIME whitelist. Kept small on purpose — Day 5's OCR (Gemini vision) is
# reliable across these three; adding heic/heif requires extra handling
# for Apple's iPhone-default format, which we'll layer on later.
_ALLOWED_MIMES: dict[str, str] = {
    "application/pdf": "pdf",
    "image/jpeg": "jpg",
    "image/png":  "png",
}

# What the client sees when they upload something we can't handle.
_MIME_ERROR = (
    "unsupported file type. Please upload a PDF, JPG, or PNG "
    "(max {mb} MB)."
)


# ---------------------------------------------------------------------------
# Storage singleton
#
# One process, one backend. Rebuilt lazily in tests via reset_storage()
# so a test can point at a temp dir without importing internals.
# ---------------------------------------------------------------------------

_storage: Optional[Storage] = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        _storage = make_storage(settings.contract_storage_root)
    return _storage


def reset_storage() -> None:
    """Test hook. Called from conftest so each test module can bind a
    fresh temp dir before the first request."""
    global _storage
    _storage = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


_SUPPORTED_LANGUAGES = {"en", "hi", "bn", "ta", "te", "kn", "mr"}
_SUPPORTED_SCRIPTS = {"native", "roman"}
# Mayura v1 register modes (confirmed via thought-translate). formal is
# the default — a "translate to Hindi" pick should mean actual Hindi
# rather than Hinglish unless the worker explicitly opts in.
_SUPPORTED_MODES = {"formal", "modern-colloquial", "classic-colloquial", "code-mixed"}


async def upload_contract(
    *,
    db: Session,
    user: User,
    upload: UploadFile,
    target_language: str,
    target_script: str = "native",
    source_language: Optional[str] = None,
    translation_mode: str = "formal",
) -> UploadedContract:
    """Validate + persist the file. Returns the DB row.

    target_language is REQUIRED — it's the language the worker wants the
    analysis rendered in (translation of Stage 3 output via Mayura runs
    only when target != 'en').

    source_language is an OPTIONAL hint for OCR — if the worker knows
    the contract's script, it lets us load the right EasyOCR reader
    instead of falling back to English + Devanagari.

    Raises HTTPException with 4xx on validation failures; DB errors
    bubble up as-is (500 by the FastAPI default handler).
    """
    target_language = (target_language or "").lower().strip()
    if target_language not in _SUPPORTED_LANGUAGES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"target_language must be one of {sorted(_SUPPORTED_LANGUAGES)}",
        )

    target_script = (target_script or "native").lower().strip()
    if target_script not in _SUPPORTED_SCRIPTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"target_script must be one of {sorted(_SUPPORTED_SCRIPTS)}",
        )

    translation_mode = (translation_mode or "formal").strip()
    if translation_mode not in _SUPPORTED_MODES:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"translation_mode must be one of {sorted(_SUPPORTED_MODES)}",
        )

    source_lang_clean: Optional[str] = None
    if source_language:
        source_lang_clean = source_language.lower().strip()
        if source_lang_clean not in _SUPPORTED_LANGUAGES:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"source_language must be one of {sorted(_SUPPORTED_LANGUAGES)} or omitted",
            )

    mime = (upload.content_type or "").lower()
    if mime not in _ALLOWED_MIMES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=_MIME_ERROR.format(mb=settings.contract_max_bytes // (1024 * 1024)),
        )

    # Read the whole file into memory. Capped at 10 MB by settings so the
    # process can afford it; the ceiling protects against a malicious
    # client that sends a truncated Content-Length + a much larger body.
    content = await upload.read()
    if len(content) == 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="empty file",
        )
    if len(content) > settings.contract_max_bytes:
        max_mb = settings.contract_max_bytes // (1024 * 1024)
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"file too large. Max {max_mb} MB.",
        )

    # DB row first so we own the id we use for the storage key. If storage
    # write fails, we roll back the row rather than leaving an orphan file.
    filename = _sanitize_filename(upload.filename or "contract")
    contract = UploadedContract(
        user_id=user.id,
        filename=filename,
        mime_type=mime,
        size_bytes=len(content),
        storage_key="",  # filled in below after we know the id
        status="uploaded",
        target_language=target_language,
        target_script=target_script,
        translation_mode=translation_mode,
        language=source_lang_clean,
    )
    db.add(contract)
    db.flush()  # populates contract.id

    ext = _ALLOWED_MIMES[mime]
    contract.storage_key = build_key(user.id, contract.id, ext)

    try:
        get_storage().save(contract.storage_key, content)
    except Exception:
        # Roll back the row before the exception propagates. Storage
        # failure means the DB has nothing to point at anyway.
        db.delete(contract)
        db.flush()
        raise

    db.flush()
    return contract


def list_contracts(
    *,
    db: Session,
    user: User,
    limit: int = 50,
    offset: int = 0,
) -> list[UploadedContract]:
    """Return the caller's uploads, newest first."""
    rows = db.execute(
        select(UploadedContract)
        .where(UploadedContract.user_id == user.id)
        .order_by(UploadedContract.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return list(rows)


def load_owned_contract(
    *,
    db: Session,
    user: User,
    contract_id: uuid.UUID,
) -> UploadedContract:
    """Ownership resolver, same pattern as sessions._load_owned_session:
    a contract belonging to another user returns 404, not 403 — the API
    isn't a probe for contract-id existence."""
    row = db.execute(
        select(UploadedContract).where(
            UploadedContract.id == contract_id,
            UploadedContract.user_id == user.id,
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="contract not found",
        )
    return row


def delete_contract(
    *,
    db: Session,
    user: User,
    contract_id: uuid.UUID,
) -> None:
    """Delete file + row. Storage delete is idempotent so a partial state
    (row gone, file dangling) is recoverable via a manual sweep — but
    that can't happen here because we delete the file first and the row
    second, and if the row delete throws we've orphaned no data."""
    contract = load_owned_contract(db=db, user=user, contract_id=contract_id)
    get_storage().delete(contract.storage_key)
    db.delete(contract)
    db.flush()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitize_filename(name: str) -> str:
    """Keep it recognisable in the UI without making it a security
    surface. Strip path separators, cap length, ensure at least
    'contract'."""
    # Strip anything the OS might interpret as a path.
    cleaned = name.replace("/", "_").replace("\\", "_").strip()
    # Drop control chars.
    cleaned = "".join(c for c in cleaned if c.isprintable())
    if not cleaned:
        cleaned = "contract"
    if len(cleaned) > 200:
        # Preserve the extension when trimming.
        head, dot, tail = cleaned.rpartition(".")
        if dot and len(tail) <= 10:
            keep = 200 - len(tail) - 1
            cleaned = f"{head[:keep]}.{tail}"
        else:
            cleaned = cleaned[:200]
    return cleaned
