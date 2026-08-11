"""
Module + access-control service functions.

Kept separate from the HTTP routes so the auth/signup path and the admin
routes can both call the same primitives (grant_access, promote_super_admin)
without pulling in FastAPI dependencies.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Module, User, UserModuleAccess


ACCESS_LEVELS = ("view", "edit", "admin")


def _access_rank(level: str) -> int:
    """Ranked view < edit < admin. Anything unknown ranks below view."""
    try:
        return ACCESS_LEVELS.index(level)
    except ValueError:
        return -1


def grant_access(
    db: Session,
    *,
    user_id: uuid.UUID,
    module_id: uuid.UUID,
    access_level: str,
    granted_by: Optional[uuid.UUID] = None,
) -> UserModuleAccess:
    """
    Grant or upgrade access. Idempotent — if a row already exists for
    (user_id, module_id) we update the access_level in place unless the
    existing level is already higher, in which case we leave it alone.
    """
    if access_level not in ACCESS_LEVELS:
        raise ValueError(f"invalid access_level: {access_level}")

    existing = db.execute(
        select(UserModuleAccess).where(
            UserModuleAccess.user_id == user_id,
            UserModuleAccess.module_id == module_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        if _access_rank(access_level) > _access_rank(existing.access_level):
            existing.access_level = access_level
            existing.granted_by = granted_by
        return existing

    row = UserModuleAccess(
        user_id=user_id,
        module_id=module_id,
        access_level=access_level,
        granted_by=granted_by,
    )
    db.add(row)
    db.flush()
    return row


def revoke_access(
    db: Session,
    *,
    user_id: uuid.UUID,
    module_id: uuid.UUID,
) -> bool:
    """Delete the access row. Returns True if a row was removed."""
    row = db.execute(
        select(UserModuleAccess).where(
            UserModuleAccess.user_id == user_id,
            UserModuleAccess.module_id == module_id,
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True


def get_module_by_key(db: Session, key: str) -> Optional[Module]:
    return db.execute(select(Module).where(Module.key == key)).scalar_one_or_none()


def maybe_promote_super_admin(db: Session, user: User) -> bool:
    """
    Bootstrap super_admin according to settings:

    1. If SUPER_ADMIN_EMAIL is set and matches the signup email → promote.
    2. Else, if no super_admin exists yet → the FIRST user to sign up
       becomes super_admin (single-tenant / demo mode).

    Returns True if the user was promoted.
    """
    if user.is_super_admin:
        return False

    configured = (settings.super_admin_email or "").strip().lower()
    if configured and user.email.lower() == configured:
        user.is_super_admin = True
        return True

    if not configured:
        existing = db.execute(
            select(User.id).where(User.is_super_admin.is_(True)).limit(1)
        ).scalar_one_or_none()
        if existing is None:
            user.is_super_admin = True
            return True

    return False


def apply_default_module_access(db: Session, user: User) -> list[str]:
    """
    Give the new user 'view' access to every module key listed in
    settings.default_module_keys. Missing modules are skipped silently
    (a listed key with no seed row is a config issue, not a signup error).

    Returns the module keys that were successfully granted.
    """
    keys = [k.strip() for k in settings.default_module_keys.split(",") if k.strip()]
    granted: list[str] = []
    for key in keys:
        module = get_module_by_key(db, key)
        if module is None:
            continue
        grant_access(
            db,
            user_id=user.id,
            module_id=module.id,
            access_level="view",
        )
        granted.append(key)
    return granted
