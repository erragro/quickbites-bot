"""
/api/contracts — Contract Reader HTTP surface.

Endpoints (all authenticated, all user-scoped):
  POST   /api/contracts                     upload a contract (multipart)
  GET    /api/contracts                     list this user's contracts
  GET    /api/contracts/{id}                get detail (incl. stages)
  DELETE /api/contracts/{id}                delete file + row

Ownership: a contract that belongs to another user returns 404 — same
pattern as /api/sessions. Never 403.

Day 5+ adds:
  POST   /api/contracts/{id}/process        kick off OCR + three-stage
  GET    /api/contracts/{id}/download       stream the original file back
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.auth.dependencies import db_session_dep, get_current_active_user
from app.contracts import processor, service as contract_service
from app.contracts.schemas import (
    ContractDetail,
    ContractSummary,
    ContractUploadResponse,
)
from app.models import User


router = APIRouter(prefix="/api/contracts", tags=["contracts"])


@router.post(
    "",
    response_model=ContractUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_contract(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
    file: Annotated[UploadFile, File()],
    target_language: Annotated[str, Form(description="BCP-47 short code the analysis should be rendered in. Required.")],
    target_script: Annotated[str, Form(description="'native' or 'roman'. Only used when target_language != 'en'.")] = "native",
    source_language: Annotated[str | None, Form(description="Optional OCR hint if the worker knows the contract's script.")] = None,
    translation_mode: Annotated[str, Form(description="Sarvam Mayura tone/register: formal | modern-colloquial | classic-colloquial | code-mixed. Default 'formal' (pure Hindi/Bengali/etc.). 'code-mixed' produces Hinglish-style output with English loanwords retained.")] = "formal",
) -> ContractUploadResponse:
    """Accept a PDF/JPG/PNG contract and persist it in 'uploaded' state.
    Does NOT auto-fire processing — the worker starts the read from the
    UI via the "Read this contract" CTA (POST /api/contracts/{id}/process).
    Split so uploads are cheap + reversible: a worker can upload
    several contracts and pick which one to analyse first (each read
    takes 30-120 seconds).

    target_language is required — it's the language the worker wants
    the analysis rendered in. Gemini does all reasoning in English;
    Mayura translates the Stage 3 output to target_language."""
    contract = await contract_service.upload_contract(
        db=db,
        user=user,
        upload=file,
        target_language=target_language,
        target_script=target_script,
        source_language=source_language,
        translation_mode=translation_mode,
    )
    return ContractUploadResponse.model_validate(contract)


@router.post(
    "/{contract_id}/process",
    response_model=ContractDetail,
    status_code=status.HTTP_202_ACCEPTED,
)
def reprocess_contract(
    contract_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
    background: BackgroundTasks,
) -> ContractDetail:
    """Manually kick off processing on an existing row. Used for retrying
    a 'failed' contract or re-running stages after prompt updates.
    Returns 202 immediately; caller polls the detail endpoint."""
    row = contract_service.load_owned_contract(
        db=db, user=user, contract_id=contract_id,
    )
    # The row already exists so no commit needed for visibility, but
    # match the upload path's shape for symmetry.
    background.add_task(processor.process_contract_bg, row.id)
    return ContractDetail.model_validate(row)


@router.get("", response_model=list[ContractSummary])
def list_contracts(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
    limit: int = 50,
    offset: int = 0,
) -> list[ContractSummary]:
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
    if offset < 0:
        raise HTTPException(400, "offset must be >= 0")
    rows = contract_service.list_contracts(
        db=db, user=user, limit=limit, offset=offset,
    )
    return [ContractSummary.model_validate(r) for r in rows]


@router.get("/{contract_id}", response_model=ContractDetail)
def get_contract(
    contract_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> ContractDetail:
    row = contract_service.load_owned_contract(
        db=db, user=user, contract_id=contract_id,
    )
    return ContractDetail.model_validate(row)


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contract(
    contract_id: uuid.UUID,
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> None:
    contract_service.delete_contract(
        db=db, user=user, contract_id=contract_id,
    )
