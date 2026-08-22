"""Contract processing orchestrator.

Advances an uploaded contract through the status machine:
    uploaded → ocr_pending → ocr_done → processing → ready
                                                  ↓
                                                failed

Each transition commits before the next stage runs so a crashed process
leaves the row at a resumable state rather than silently reverting to
'uploaded'. The status field is what the UI polls; the `stages` JSONB
accumulates output progressively so the viewer can render whatever's
ready (OCR text alone is useful even while Stage 1 is still running).

Runs as a FastAPI BackgroundTask — same worker, response already sent
to the client. Each invocation opens its own db_session because the
request that scheduled it has already been torn down by the time this
runs.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.contracts import ocr as ocr_mod
from app.contracts import stage1 as stage1_mod
from app.contracts import stage2 as stage2_mod
from app.contracts import stage3 as stage3_mod
from app.contracts import translate as translate_mod
from app.contracts.service import get_storage
from app.db import db_session
from app.models import UploadedContract


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Entry point (background-task wrapper)
# ---------------------------------------------------------------------------


def process_contract_bg(contract_id: uuid.UUID) -> None:
    """BackgroundTask entry. Opens its own db_session, delegates to the
    real driver. Swallows exceptions after logging them — a background
    task raising kills the worker's task queue but nothing user-facing
    is waiting on this, so degrading to 'failed' status is preferable
    to bringing down the worker."""
    try:
        with db_session() as db:
            process_contract(db, contract_id)
    except Exception:
        logger.exception("contract %s processing failed at top level", contract_id)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def process_contract(db: Session, contract_id: uuid.UUID) -> None:
    """Advance the contract through OCR → Stage 1. Idempotent: re-running
    on a 'ready' row rewrites stages from scratch; re-running on a
    'failed' row clears the error and tries again."""
    contract = db.execute(
        select(UploadedContract).where(UploadedContract.id == contract_id)
    ).scalar_one_or_none()
    if contract is None:
        logger.warning("contract %s not found; nothing to process", contract_id)
        return

    _reset(contract)
    _commit(db)

    # ---------- OCR ----------
    _advance(db, contract, status="ocr_pending")
    try:
        file_bytes = get_storage().load(contract.storage_key)
    except FileNotFoundError:
        _fail(db, contract, "file missing in storage")
        return
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("contract %s: storage read failed", contract_id)
        _fail(db, contract, f"could not read file: {exc}")
        return

    try:
        # Pass the row's source-language hint to EasyOCR so it loads the
        # matching Reader (English + one Indic script per reader). The
        # `language` column is the source hint from the upload form; if
        # unset we default to English + Devanagari in ocr.extract_text.
        ocr_result = ocr_mod.extract_text(
            file_bytes,
            contract.mime_type,
            source_language=contract.language,
        )
    except Exception as exc:
        logger.exception("contract %s: OCR failed", contract_id)
        _fail(db, contract, f"OCR failed: {exc}")
        return

    if not ocr_result.text:
        _fail(db, contract, "OCR returned no text — try a clearer photo")
        return

    contract.ocr_text = ocr_result.text
    if ocr_result.language and not contract.language:
        contract.language = ocr_result.language
    _advance(db, contract, status="ocr_done")

    # ---------- Stage 1 ----------
    _advance(db, contract, status="processing")
    try:
        stage_1_out = stage1_mod.analyse(
            ocr_result.text,
            language=ocr_result.language or "en",
        )
    except Exception as exc:
        logger.exception("contract %s: Stage 1 failed", contract_id)
        _fail(db, contract, f"Stage 1 failed: {exc}")
        return

    stages = _merge_stages(contract.stages, {"stage_1": stage_1_out})
    contract.stages = stages
    contract.contract_type = stage_1_out.get("contract_type") or "unknown"
    _commit(db)

    # ---------- Stage 2 (Research — statute + risk) ----------
    try:
        stage_2_out = stage2_mod.annotate(stage_1_out)
    except Exception as exc:
        logger.exception("contract %s: Stage 2 failed", contract_id)
        # Stage 2 failure is soft — we can still ship Stage 1 output.
        # Persist the error but continue to Stage 3 with an empty
        # annotations set (Stage 3's backfill produces amber defaults).
        stage_2_out = {"annotations": [], "error": f"Stage 2 failed: {exc}"}

    stages = _merge_stages(contract.stages, {"stage_2": stage_2_out})
    contract.stages = stages
    _commit(db)

    # ---------- Stage 3 (Synthesise — worker-facing rendition in English) ----------
    try:
        stage_3_out = stage3_mod.synthesise(stage_1_out, stage_2_out)
    except Exception as exc:
        logger.exception("contract %s: Stage 3 failed", contract_id)
        # Stage 3 failure is soft — Stage 1 + Stage 2 alone are still
        # useful (viewer can show original text + risk pill).
        stage_3_out = {"rendered": [], "error": f"Stage 3 failed: {exc}"}

    stages = _merge_stages(contract.stages, {"stage_3": stage_3_out})
    contract.stages = stages
    _commit(db)

    # ---------- Translate (Mayura → worker's chosen target language) ----------
    # Skipped when target == 'en' (Stage 3 output is already the target),
    # or when Stage 3 has nothing to translate. Failure is soft: the row
    # still becomes 'ready' with English fallback; the viewer picks it
    # up because it always falls back to stages.stage_3.rendered when
    # translation.rendered is missing.
    target = (contract.target_language or "en").lower()
    mode = (contract.translation_mode or "formal").strip()
    logger.info(
        "contract %s: translate check: target=%r mode=%r rendered_count=%s",
        contract_id, target, mode, len(stage_3_out.get("rendered") or []),
    )
    if target != "en" and stage_3_out.get("rendered"):
        logger.info(
            "contract %s: translating to %s via Mayura (mode=%s)",
            contract_id, target, mode,
        )
        try:
            translated = translate_mod.translate_stage_3(
                stage_3_out["rendered"],
                target_language=target,
                mode=mode,
            )
            stage_3_out["translation"] = {
                "language": target,
                "mode": mode,
                "rendered": translated,
                "translator": "sarvam/mayura:v1",
                "error": None,
            }
        except translate_mod.TranslationError as exc:
            logger.warning(
                "contract %s: translation to %s failed: %s",
                contract_id, target, exc,
            )
            stage_3_out["translation"] = {
                "language": target,
                "rendered": None,
                "translator": "sarvam/mayura:v1",
                "error": str(exc),
            }
        except Exception as exc:
            logger.exception("contract %s: translation raised unexpectedly", contract_id)
            stage_3_out["translation"] = {
                "language": target,
                "rendered": None,
                "translator": "sarvam/mayura:v1",
                "error": f"unexpected: {exc}",
            }
        # Persist the updated stages.stage_3 with translation attached.
        stages = _merge_stages(contract.stages, {"stage_3": stage_3_out})
        contract.stages = stages
        # Belt + braces: even with a fresh top-level dict from
        # _merge_stages, some SQLAlchemy versions have failed to detect
        # this as a change against a JSONB column when the previous
        # value shared internal identity. flag_modified is the
        # canonical safe hammer.
        flag_modified(contract, "stages")

    _advance(db, contract, status="ready")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _reset(contract: UploadedContract) -> None:
    """Clear any prior error state so a re-process starts clean."""
    contract.error_message = None
    contract.updated_at = datetime.now(timezone.utc)


def _advance(db: Session, contract: UploadedContract, *, status: str) -> None:
    """Set status + commit. Frontend's poll picks up the change on the
    next tick, so the pill animates through the stages instead of jumping
    from 'uploaded' straight to 'ready'."""
    contract.status = status
    contract.updated_at = datetime.now(timezone.utc)
    _commit(db)


def _fail(db: Session, contract: UploadedContract, message: str) -> None:
    contract.status = "failed"
    contract.error_message = message
    contract.updated_at = datetime.now(timezone.utc)
    _commit(db)
    logger.info("contract %s marked failed: %s", contract.id, message)


def _commit(db: Session) -> None:
    """Commit + reset the session so the next stage sees a clean state."""
    db.commit()


def _merge_stages(
    existing: dict[str, Any] | None,
    additions: dict[str, Any],
) -> dict[str, Any]:
    """Merge additions into the existing stages dict without wiping
    prior stages. `existing` may be None (first stage) or a JSONB dict.

    Deep-copies the additions so the returned dict shares no nested
    references with `existing`. Without this, mutating an entry in the
    additions dict (e.g. later adding a translation to stage_3_out
    after we've already merged it into stages once) leaves SQLAlchemy
    unable to detect the change — the JSONB column compares by
    reference for the top-level dict and finds it identical."""
    import copy
    merged: dict[str, Any] = dict(existing) if existing else {}
    merged.update(copy.deepcopy(additions))
    return merged
