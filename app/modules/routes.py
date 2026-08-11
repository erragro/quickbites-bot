"""
/api/modules — read-only surface for any authenticated user.

Returns every registered module with the caller's access_level joined in.
Frontend uses this to render the main sidebar (a module the caller has no
access to is present in the response with access_level=null; the frontend
chooses whether to hide it or show it disabled).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import db_session_dep, get_current_active_user
from app.models import Module, User, UserModuleAccess
from app.modules.schemas import ModuleWithAccess


router = APIRouter(prefix="/api/modules", tags=["modules"])


@router.get("", response_model=list[ModuleWithAccess])
def list_modules(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> list[ModuleWithAccess]:
    modules = db.execute(
        select(Module).order_by(Module.sort_order.asc(), Module.name.asc())
    ).scalars().all()

    # Fetch all of the user's access rows in a single query, then join in
    # Python. Fewer, wider queries beat N+1 for a table this small.
    access_rows = db.execute(
        select(UserModuleAccess).where(UserModuleAccess.user_id == user.id)
    ).scalars().all()
    access_by_module = {row.module_id: row.access_level for row in access_rows}

    out: list[ModuleWithAccess] = []
    for m in modules:
        # Super-admin implicitly has 'admin' access to everything — this is
        # the single place the flag short-circuits the ACL, so both the
        # backend admin routes and the frontend sidebar agree.
        if user.is_super_admin:
            level = "admin"
        else:
            level = access_by_module.get(m.id)
        payload = ModuleWithAccess.model_validate(m)
        payload.access_level = level  # type: ignore[assignment]
        out.append(payload)
    return out
