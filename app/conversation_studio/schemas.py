"""Pydantic DTOs for the chip-tap conversation layer."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Public (chip-tap) read models
# ---------------------------------------------------------------------------


class IssueTypeChip(BaseModel):
    """Leaf shown to the customer as a tappable chip."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    sort_order: int


class BusinessUnitTree(BaseModel):
    """A business unit + the issue types under it (single-level for now).
    If we later wire sub-units, `children` gets populated with more units."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    icon: Optional[str] = None
    sort_order: int
    issue_types: list[IssueTypeChip] = Field(default_factory=list)
    children: list["BusinessUnitTree"] = Field(default_factory=list)


class ChatStartersResponse(BaseModel):
    """Full chip tree returned to the frontend on `/api/chat/starters`."""

    business_units: list[BusinessUnitTree]


# ---------------------------------------------------------------------------
# Select-issue request/response — the chip-tap turn
# ---------------------------------------------------------------------------


class SelectIssueRequest(BaseModel):
    issue_type_id: uuid.UUID
    # Optional: a customer_id if the frontend can supply one from context
    # (e.g. currently-logged-in customer profile). Lets the enricher pull
    # customer data even if no order has been mentioned yet.
    customer_id: Optional[int] = Field(default=None, ge=1)
    order_id: Optional[int] = Field(default=None, ge=1)


class SelectIssueResponse(BaseModel):
    session_id: str
    issue_type_id: uuid.UUID
    business_unit_id: uuid.UUID
    acknowledgment: str
    # Which data points actually resolved (vs configured). Useful for the
    # UI to know if it should prompt the customer for an order id.
    resolved_data_points: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Admin CRUD DTOs (used by the admin panel later)
# ---------------------------------------------------------------------------


class BusinessUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    icon: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None
    sort_order: int
    is_active: bool
    created_at: datetime


class DataPointOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    description: Optional[str] = None
    fetcher_ref: str
    is_system: bool
    created_at: datetime


class IssueTypeDataPointBinding(BaseModel):
    data_point_id: uuid.UUID
    is_required: bool = True
    sort_order: int = 100


class IssueTypeAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_unit_id: uuid.UUID
    code: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    routes_to_intent: Optional[str] = None
    sort_order: int
    is_active: bool
    data_points: list[IssueTypeDataPointBinding] = Field(default_factory=list)


class AcknowledgmentTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    issue_type_id: uuid.UUID
    template: str
    weight: int
    is_active: bool
    created_at: datetime
