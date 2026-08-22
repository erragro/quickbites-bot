"""Pydantic DTOs for the Contract Reader HTTP surface."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ContractSummary(BaseModel):
    """Row-level view for the contracts list. No `stages` payload — that
    can be several kilobytes per row and the list view never renders it."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    language: Optional[str] = None
    target_language: str
    target_script: str
    translation_mode: str
    contract_type: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ContractDetail(ContractSummary):
    """Full contract row. Includes the raw OCR text + the three-stage LLM
    output. Consumers should render whichever stages are present rather
    than requiring all of them."""

    ocr_text: Optional[str] = None
    stages: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


class ContractUploadResponse(BaseModel):
    """What POST /api/contracts returns. Same shape as ContractDetail but
    the file's just landed — stages/ocr_text/language/contract_type will
    all be None until the day-5 processor advances the status machine."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    mime_type: str
    size_bytes: int
    status: str
    created_at: datetime
