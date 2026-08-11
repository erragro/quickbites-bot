"""
/api/admin/* — super-admin-only management surface.

Endpoints:
  GET    /api/admin/users                    list users + module accesses
  GET    /api/admin/users/{user_id}          single user + accesses
  PATCH  /api/admin/users/{user_id}          toggle is_active / is_super_admin
  POST   /api/admin/users/{user_id}/access   grant module access
  DELETE /api/admin/users/{user_id}/access/{module_id}
                                             revoke access
  GET    /api/admin/modules                  full module list (incl. metadata)
  POST   /api/admin/modules                  register a new module

Every route below is guarded with `require_super_admin` so calling as a
regular user returns 403 (never 200 with empty data — clarity beats
silent-success on admin surfaces).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import db_session_dep, get_current_active_user
from app.models import Module, User, UserModuleAccess
from app.modules.schemas import (
    AccessGrant,
    ModuleCreate,
    ModuleOut,
    UserAdminOut,
    UserAdminUpdate,
    UserModuleAccessOut,
)
from app.modules.service import grant_access, revoke_access


router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_super_admin(
    user: Annotated[User, Depends(get_current_active_user)],
) -> User:
    if not user.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="super-admin only",
        )
    return user


def _serialize_user(user: User) -> UserAdminOut:
    """Hand-serialize because we need to project the module join in."""
    accesses = []
    for a in user.module_accesses:
        accesses.append(
            UserModuleAccessOut(
                module_id=a.module_id,
                module_key=a.module.key,
                module_name=a.module.name,
                access_level=a.access_level,  # type: ignore[arg-type]
                granted_at=a.granted_at,
                granted_by=a.granted_by,
            )
        )
    return UserAdminOut(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        is_super_admin=user.is_super_admin,
        created_at=user.created_at,
        module_accesses=accesses,
    )


# --- Users ------------------------------------------------------------------


@router.get("/users", response_model=list[UserAdminOut])
def list_users(
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
    limit: int = 100,
    offset: int = 0,
) -> list[UserAdminOut]:
    if limit < 1 or limit > 500 or offset < 0:
        raise HTTPException(400, "invalid limit or offset")
    users = db.execute(
        select(User)
        .options(
            selectinload(User.module_accesses).selectinload(UserModuleAccess.module),
        )
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return [_serialize_user(u) for u in users]


def _load_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.execute(
        select(User)
        .options(
            selectinload(User.module_accesses).selectinload(UserModuleAccess.module),
        )
        .where(User.id == user_id)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="user not found")
    return user


@router.get("/users/{user_id}", response_model=UserAdminOut)
def get_user(
    user_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> UserAdminOut:
    return _serialize_user(_load_user(db, user_id))


@router.patch("/users/{user_id}", response_model=UserAdminOut)
def update_user(
    user_id: uuid.UUID,
    body: UserAdminUpdate,
    admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> UserAdminOut:
    user = _load_user(db, user_id)

    # Guard against demoting the last super_admin — leaves the platform
    # unmanageable and there's no way to recover through the API.
    if body.is_super_admin is False and user.is_super_admin:
        remaining = db.execute(
            select(User.id).where(
                User.is_super_admin.is_(True),
                User.id != user.id,
            )
        ).first()
        if remaining is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="cannot demote the last super-admin",
            )

    # Guard against a super_admin locking themselves out via is_active.
    if body.is_active is False and user.id == admin.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="cannot deactivate your own account",
        )

    if body.is_active is not None:
        user.is_active = body.is_active
    if body.is_super_admin is not None:
        user.is_super_admin = body.is_super_admin

    db.flush()
    return _serialize_user(user)


@router.post(
    "/users/{user_id}/access",
    response_model=UserAdminOut,
    status_code=status.HTTP_201_CREATED,
)
def grant_module_access(
    user_id: uuid.UUID,
    body: AccessGrant,
    admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> UserAdminOut:
    _load_user(db, user_id)  # 404 if missing
    module = db.execute(
        select(Module).where(Module.id == body.module_id)
    ).scalar_one_or_none()
    if module is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="module not found")

    grant_access(
        db,
        user_id=user_id,
        module_id=body.module_id,
        access_level=body.access_level,
        granted_by=admin.id,
    )
    return _serialize_user(_load_user(db, user_id))


@router.delete(
    "/users/{user_id}/access/{module_id}",
    response_model=UserAdminOut,
)
def revoke_module_access(
    user_id: uuid.UUID,
    module_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> UserAdminOut:
    _load_user(db, user_id)  # 404 if missing
    removed = revoke_access(db, user_id=user_id, module_id=module_id)
    if not removed:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail="no such access grant",
        )
    return _serialize_user(_load_user(db, user_id))


# --- Modules ----------------------------------------------------------------


@router.get("/modules", response_model=list[ModuleOut])
def list_modules_admin(
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> list[ModuleOut]:
    rows = db.execute(
        select(Module).order_by(Module.sort_order.asc(), Module.name.asc())
    ).scalars().all()
    return [ModuleOut.model_validate(m) for m in rows]


@router.post("/modules", response_model=ModuleOut, status_code=status.HTTP_201_CREATED)
def register_module(
    body: ModuleCreate,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> ModuleOut:
    module = Module(
        key=body.key,
        name=body.name,
        description=body.description,
        icon=body.icon,
        path=body.path,
        sort_order=body.sort_order,
        is_system=False,  # admin-panel-registered modules are always non-system
    )
    db.add(module)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"module key '{body.key}' already exists",
        )
    return ModuleOut.model_validate(module)
