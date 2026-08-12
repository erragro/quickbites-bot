"""
Super-admin CRUD for the Conversation Studio.

  GET    /api/admin/conversation/business-units
  POST   /api/admin/conversation/business-units
  PATCH  /api/admin/conversation/business-units/{id}
  DELETE /api/admin/conversation/business-units/{id}

  GET    /api/admin/conversation/issue-types
  POST   /api/admin/conversation/issue-types
  PATCH  /api/admin/conversation/issue-types/{id}
  DELETE /api/admin/conversation/issue-types/{id}
  PUT    /api/admin/conversation/issue-types/{id}/data-points   (replace bindings)

  GET    /api/admin/conversation/data-points                (registry, read-only)

  GET    /api/admin/conversation/issue-types/{id}/templates
  POST   /api/admin/conversation/issue-types/{id}/templates
  PATCH  /api/admin/conversation/templates/{id}
  DELETE /api/admin/conversation/templates/{id}

All routes require super_admin. Data-point registry is READ-ONLY through
the API because each entry maps to a Python callable — new callables
require a code deploy (see app/conversation_studio/service.py::FETCHER_REGISTRY).
"""

from __future__ import annotations

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import db_session_dep
from app.conversation_studio.schemas import (
    AcknowledgmentTemplateOut,
    BusinessUnitOut,
    DataPointOut,
    IssueTypeAdminOut,
    IssueTypeDataPointBinding,
)
from app.conversation_studio.service import FETCHER_REGISTRY
from app.models import (
    AcknowledgmentTemplate,
    BusinessUnit,
    DataPoint,
    IssueType,
    IssueTypeDataPoint,
    User,
)
from app.modules.admin_routes import require_super_admin


router = APIRouter(
    prefix="/api/admin/conversation",
    tags=["admin-conversation"],
)


# Known Stage 2 matrix intents. Admins can only route an issue type to
# one of these (or null = no matrix routing → falls through to safety
# net). Mirrors the intent enum in app/schemas.py.
_MATRIX_INTENTS = {
    "missing_item", "wrong_order", "cold_food",
    "never_arrived", "rider_late", "rider_rude", "rider_demanded_tip",
    "double_charge", "promo_failed",
    "cancel_request", "human_request", "vague", "other",
}


# ============================================================================
# Business Units
# ============================================================================


class BusinessUnitCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(..., min_length=1, max_length=100)
    icon: Optional[str] = Field(default=None, max_length=50)
    parent_id: Optional[uuid.UUID] = None
    sort_order: int = 100


class BusinessUnitUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    icon: Optional[str] = Field(default=None, max_length=50)
    parent_id: Optional[uuid.UUID] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


@router.get("/business-units", response_model=list[BusinessUnitOut])
def list_business_units(
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> list[BusinessUnitOut]:
    rows = db.execute(
        select(BusinessUnit).order_by(
            BusinessUnit.sort_order.asc(), BusinessUnit.name.asc(),
        )
    ).scalars().all()
    return [BusinessUnitOut.model_validate(r) for r in rows]


@router.post(
    "/business-units",
    response_model=BusinessUnitOut,
    status_code=status.HTTP_201_CREATED,
)
def create_business_unit(
    body: BusinessUnitCreate,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> BusinessUnitOut:
    bu = BusinessUnit(
        code=body.code,
        name=body.name,
        icon=body.icon,
        parent_id=body.parent_id,
        sort_order=body.sort_order,
    )
    db.add(bu)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"business unit with code '{body.code}' already exists",
        )
    return BusinessUnitOut.model_validate(bu)


def _load_bu(db: Session, bu_id: uuid.UUID) -> BusinessUnit:
    bu = db.execute(
        select(BusinessUnit).where(BusinessUnit.id == bu_id)
    ).scalar_one_or_none()
    if bu is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "business unit not found")
    return bu


@router.patch("/business-units/{bu_id}", response_model=BusinessUnitOut)
def update_business_unit(
    bu_id: uuid.UUID,
    body: BusinessUnitUpdate,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> BusinessUnitOut:
    bu = _load_bu(db, bu_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(bu, field, value)
    db.flush()
    return BusinessUnitOut.model_validate(bu)


@router.delete(
    "/business-units/{bu_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_business_unit(
    bu_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> None:
    bu = _load_bu(db, bu_id)
    # Reject if there are still issue types attached — surfaces the
    # actual cost of a delete instead of silently cascading. Admin has
    # to move or delete the issue types first.
    remaining = db.execute(
        select(IssueType.id).where(IssueType.business_unit_id == bu.id).limit(1)
    ).scalar_one_or_none()
    if remaining is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="cannot delete a business unit that still has issue types",
        )
    db.delete(bu)
    db.flush()


# ============================================================================
# Issue Types
# ============================================================================


class IssueTypeCreate(BaseModel):
    business_unit_id: uuid.UUID
    code: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(..., min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    icon: Optional[str] = Field(default=None, max_length=50)
    routes_to_intent: Optional[str] = Field(default=None, max_length=50)
    sort_order: int = 100


class IssueTypeUpdate(BaseModel):
    business_unit_id: Optional[uuid.UUID] = None
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    description: Optional[str] = Field(default=None, max_length=1000)
    icon: Optional[str] = Field(default=None, max_length=50)
    routes_to_intent: Optional[str] = Field(default=None, max_length=50)
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None


class DataPointBindingsReplace(BaseModel):
    bindings: list[IssueTypeDataPointBinding]


def _validate_intent(intent: Optional[str]) -> None:
    if intent is None or intent == "":
        return
    if intent not in _MATRIX_INTENTS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=(
                f"'routes_to_intent' must be one of {sorted(_MATRIX_INTENTS)} "
                "or null"
            ),
        )


def _serialize_issue_type(it: IssueType) -> IssueTypeAdminOut:
    return IssueTypeAdminOut(
        id=it.id,
        business_unit_id=it.business_unit_id,
        code=it.code,
        name=it.name,
        description=it.description,
        icon=it.icon,
        routes_to_intent=it.routes_to_intent,
        sort_order=it.sort_order,
        is_active=it.is_active,
        data_points=[
            IssueTypeDataPointBinding(
                data_point_id=b.data_point_id,
                is_required=b.is_required,
                sort_order=b.sort_order,
            )
            for b in sorted(it.data_point_links, key=lambda x: x.sort_order)
        ],
    )


def _load_issue_type(db: Session, it_id: uuid.UUID) -> IssueType:
    it = db.execute(
        select(IssueType)
        .options(selectinload(IssueType.data_point_links))
        .where(IssueType.id == it_id)
    ).scalar_one_or_none()
    if it is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "issue type not found")
    return it


@router.get("/issue-types", response_model=list[IssueTypeAdminOut])
def list_issue_types(
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> list[IssueTypeAdminOut]:
    rows = db.execute(
        select(IssueType)
        .options(selectinload(IssueType.data_point_links))
        .order_by(IssueType.sort_order.asc(), IssueType.name.asc())
    ).scalars().all()
    return [_serialize_issue_type(it) for it in rows]


@router.post(
    "/issue-types",
    response_model=IssueTypeAdminOut,
    status_code=status.HTTP_201_CREATED,
)
def create_issue_type(
    body: IssueTypeCreate,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> IssueTypeAdminOut:
    _validate_intent(body.routes_to_intent)
    # Parent BU must exist so we don't silently orphan.
    _load_bu(db, body.business_unit_id)
    it = IssueType(
        business_unit_id=body.business_unit_id,
        code=body.code,
        name=body.name,
        description=body.description,
        icon=body.icon,
        routes_to_intent=body.routes_to_intent or None,
        sort_order=body.sort_order,
    )
    db.add(it)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"issue type with code '{body.code}' already exists under this business unit",
        )
    return _serialize_issue_type(
        db.execute(
            select(IssueType).options(selectinload(IssueType.data_point_links))
            .where(IssueType.id == it.id)
        ).scalar_one()
    )


@router.patch("/issue-types/{it_id}", response_model=IssueTypeAdminOut)
def update_issue_type(
    it_id: uuid.UUID,
    body: IssueTypeUpdate,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> IssueTypeAdminOut:
    it = _load_issue_type(db, it_id)
    fields = body.model_dump(exclude_unset=True)
    if "routes_to_intent" in fields:
        _validate_intent(fields["routes_to_intent"])
        if fields["routes_to_intent"] == "":
            fields["routes_to_intent"] = None
    if "business_unit_id" in fields and fields["business_unit_id"] is not None:
        _load_bu(db, fields["business_unit_id"])
    for k, v in fields.items():
        setattr(it, k, v)
    db.flush()
    return _serialize_issue_type(it)


@router.delete(
    "/issue-types/{it_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_issue_type(
    it_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> None:
    it = _load_issue_type(db, it_id)
    db.delete(it)
    db.flush()


@router.put(
    "/issue-types/{it_id}/data-points",
    response_model=IssueTypeAdminOut,
)
def replace_data_point_bindings(
    it_id: uuid.UUID,
    body: DataPointBindingsReplace,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> IssueTypeAdminOut:
    """
    Replace the full set of data-point bindings for this issue type.
    Simpler than delta-CRUD for the admin flow: the UI edits a
    checklist + reorder locally and PUTs the whole set.
    """
    it = _load_issue_type(db, it_id)

    # Validate every referenced data point exists.
    if body.bindings:
        seen = set()
        for b in body.bindings:
            if b.data_point_id in seen:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    detail=f"duplicate binding for data point {b.data_point_id}",
                )
            seen.add(b.data_point_id)
        found_ids = {
            row for (row,) in db.execute(
                select(DataPoint.id).where(DataPoint.id.in_(seen))
            ).all()
        }
        missing = seen - found_ids
        if missing:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"unknown data points: {sorted(str(x) for x in missing)}",
            )

    # Wipe and re-insert. Small collection (5-10 rows typical), simpler
    # than diffing.
    for existing in list(it.data_point_links):
        db.delete(existing)
    db.flush()
    for b in body.bindings:
        db.add(
            IssueTypeDataPoint(
                issue_type_id=it.id,
                data_point_id=b.data_point_id,
                is_required=b.is_required,
                sort_order=b.sort_order,
            )
        )
    db.flush()
    # SQLAlchemy caches the (now stale) data_point_links relationship
    # collection in the identity map — a subsequent SELECT with
    # selectinload would return the cached empty list. Explicit expire
    # forces the next access to re-fetch.
    db.expire(it, ["data_point_links"])
    return _serialize_issue_type(it)


# ============================================================================
# Data Points (read-only registry)
# ============================================================================


@router.get("/data-points", response_model=list[DataPointOut])
def list_data_points(
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> list[DataPointOut]:
    """
    Registry of Python fetchers exposed to the admin. Not writable via
    the API — every entry maps to a callable in
    app/conversation_studio/service.py::FETCHER_REGISTRY. Adding a new
    fetcher requires a code deploy.
    """
    rows = db.execute(
        select(DataPoint).order_by(DataPoint.name.asc())
    ).scalars().all()
    # Cheap health signal in the response: which registry entries
    # actually have a callable behind them right now. Frontend can
    # warn if an admin binds an issue type to a stale fetcher_ref.
    payload: list[DataPointOut] = []
    for r in rows:
        d = DataPointOut.model_validate(r)
        # Attach a marker via the description if the fetcher is missing
        # from FETCHER_REGISTRY. Keeps the response schema stable while
        # surfacing the issue somewhere visible.
        if r.fetcher_ref not in FETCHER_REGISTRY:
            d.description = f"[⚠ no active fetcher] {d.description or ''}".strip()
        payload.append(d)
    return payload


# ============================================================================
# Acknowledgment Templates
# ============================================================================


class TemplateCreate(BaseModel):
    template: str = Field(..., min_length=1, max_length=2000)
    weight: int = Field(default=1, ge=1, le=100)
    is_active: bool = True


class TemplateUpdate(BaseModel):
    template: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    weight: Optional[int] = Field(default=None, ge=1, le=100)
    is_active: Optional[bool] = None


@router.get(
    "/issue-types/{it_id}/templates",
    response_model=list[AcknowledgmentTemplateOut],
)
def list_templates(
    it_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> list[AcknowledgmentTemplateOut]:
    _load_issue_type(db, it_id)  # 404 if missing
    rows = db.execute(
        select(AcknowledgmentTemplate)
        .where(AcknowledgmentTemplate.issue_type_id == it_id)
        .order_by(AcknowledgmentTemplate.created_at.asc())
    ).scalars().all()
    return [AcknowledgmentTemplateOut.model_validate(r) for r in rows]


@router.post(
    "/issue-types/{it_id}/templates",
    response_model=AcknowledgmentTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
def create_template(
    it_id: uuid.UUID,
    body: TemplateCreate,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> AcknowledgmentTemplateOut:
    _load_issue_type(db, it_id)
    row = AcknowledgmentTemplate(
        issue_type_id=it_id,
        template=body.template,
        weight=body.weight,
        is_active=body.is_active,
    )
    db.add(row)
    db.flush()
    return AcknowledgmentTemplateOut.model_validate(row)


def _load_template(db: Session, t_id: uuid.UUID) -> AcknowledgmentTemplate:
    row = db.execute(
        select(AcknowledgmentTemplate).where(AcknowledgmentTemplate.id == t_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")
    return row


@router.patch("/templates/{t_id}", response_model=AcknowledgmentTemplateOut)
def update_template(
    t_id: uuid.UUID,
    body: TemplateUpdate,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> AcknowledgmentTemplateOut:
    row = _load_template(db, t_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.flush()
    return AcknowledgmentTemplateOut.model_validate(row)


@router.delete(
    "/templates/{t_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_template(
    t_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> None:
    row = _load_template(db, t_id)
    db.delete(row)
    db.flush()
