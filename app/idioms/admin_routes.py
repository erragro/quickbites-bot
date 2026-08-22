"""
/api/admin/idioms/* — super-admin CRUD for the idiom library.

Endpoints (all guarded by require_super_admin):
  GET    /api/admin/idioms                    list all idioms (with translations)
  POST   /api/admin/idioms                    create new idiom + optional translations
  GET    /api/admin/idioms/{id}               single idiom
  PATCH  /api/admin/idioms/{id}               update idiom fields
  DELETE /api/admin/idioms/{id}               hard delete (cascades to translations)
  PUT    /api/admin/idioms/{id}/translations/{lang}
                                              upsert a per-language translation
  DELETE /api/admin/idioms/{id}/translations/{lang}
                                              remove a per-language translation

Cache invalidation: every write endpoint calls translate.idioms.reset_cache()
so the runtime Aho-Corasick automaton reloads on the next translation.
Reads don't touch the cache.

Multi-tenant note: for v1 we treat NULL tenant_id as "shared". A future
per-tenant override path would pass the current user's tenant_id to
both the create constraint and the reset scope; today we keep it simple
and let the unique constraint (source_phrase, tenant_id) block
duplicates within the shared pool.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import db_session_dep, get_current_active_user
from app.idioms.schemas import (
    IdiomCreate,
    IdiomOut,
    IdiomTranslationOut,
    IdiomTranslationUpsert,
    IdiomUpdate,
)
from app.models import Idiom, IdiomTranslation, User
from app.modules.admin_routes import require_super_admin
from app.translate import idioms as idiom_runtime


router = APIRouter(prefix="/api/admin/idioms", tags=["admin-idioms"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load(db: Session, idiom_id: uuid.UUID) -> Idiom:
    """404-or-return. Eager-loads translations because every serialization
    path we have needs them."""
    row = db.execute(
        select(Idiom)
        .options(selectinload(Idiom.translations))
        .where(Idiom.id == idiom_id)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="idiom not found")
    return row


def _serialize(row: Idiom) -> IdiomOut:
    return IdiomOut(
        id=row.id,
        source_phrase=row.source_phrase,
        meaning=row.meaning,
        category=row.category,
        is_active=row.is_active,
        created_at=row.created_at,
        updated_at=row.updated_at,
        translations=[
            IdiomTranslationOut.model_validate(t) for t in row.translations
        ],
    )


# ---------------------------------------------------------------------------
# Idiom endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=list[IdiomOut])
def list_idioms(
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
    category: str | None = None,
    active_only: bool = False,
    limit: int = 500,
    offset: int = 0,
) -> list[IdiomOut]:
    if limit < 1 or limit > 2000 or offset < 0:
        raise HTTPException(400, "invalid limit or offset")

    stmt = (
        select(Idiom)
        .options(selectinload(Idiom.translations))
        .order_by(Idiom.category.asc(), Idiom.source_phrase.asc())
        .limit(limit)
        .offset(offset)
    )
    if category:
        stmt = stmt.where(Idiom.category == category.lower())
    if active_only:
        stmt = stmt.where(Idiom.is_active.is_(True))

    rows = db.execute(stmt).scalars().all()
    return [_serialize(r) for r in rows]


@router.post("", response_model=IdiomOut, status_code=status.HTTP_201_CREATED)
def create_idiom(
    body: IdiomCreate,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> IdiomOut:
    # Postgres treats NULL tenant_id values as distinct in a UNIQUE
    # constraint (SQL-standard NULLS DISTINCT semantics), so the DB
    # constraint alone won't stop two shared-tenant (NULL) duplicates.
    # For v1 all rows are shared, so we do an explicit case-insensitive
    # existence check here. When we add per-tenant idioms this same
    # query gets scoped by tenant_id.
    # `.first()` not `.scalar_one_or_none()` — the point is to reject
    # a duplicate insert, so tolerating N existing rows (from earlier
    # test runs that got past the check) is fine.
    existing = db.execute(
        select(Idiom).where(
            Idiom.source_phrase.ilike(body.source_phrase),
            Idiom.tenant_id.is_(None),
        )
    ).first()
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"idiom already exists: {body.source_phrase!r}",
        )

    idiom = Idiom(
        source_phrase=body.source_phrase,
        meaning=body.meaning,
        category=body.category,
        is_active=body.is_active,
    )
    db.add(idiom)
    try:
        db.flush()
    except IntegrityError:
        # Defensive — a concurrent create with the exact same phrase
        # + non-null tenant could still hit the DB constraint.
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail=f"idiom already exists: {body.source_phrase!r}",
        )

    # Attach any bootstrap translations. Duplicates across languages
    # within the payload get caught by the composite unique constraint.
    seen_langs: set[str] = set()
    for t in body.translations:
        if t.language in seen_langs:
            db.rollback()
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail=f"duplicate translation for language {t.language!r}",
            )
        seen_langs.add(t.language)
        db.add(IdiomTranslation(
            idiom_id=idiom.id,
            language=t.language,
            translation=t.translation,
            notes=t.notes,
            is_active=t.is_active,
        ))
    db.flush()

    # Force the ORM to refresh the collection so the response includes
    # the just-inserted translations rather than the empty cached one.
    db.expire(idiom, ["translations"])

    idiom_runtime.reset_cache()
    return _serialize(_load(db, idiom.id))


@router.get("/{idiom_id}", response_model=IdiomOut)
def get_idiom(
    idiom_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> IdiomOut:
    return _serialize(_load(db, idiom_id))


@router.patch("/{idiom_id}", response_model=IdiomOut)
def update_idiom(
    idiom_id: uuid.UUID,
    body: IdiomUpdate,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> IdiomOut:
    idiom = _load(db, idiom_id)
    if body.source_phrase is not None:
        idiom.source_phrase = body.source_phrase.strip()
    if body.meaning is not None:
        idiom.meaning = body.meaning
    if body.category is not None:
        idiom.category = body.category
    if body.is_active is not None:
        idiom.is_active = body.is_active
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="another idiom already uses this source_phrase",
        )
    idiom_runtime.reset_cache()
    return _serialize(idiom)


@router.delete("/{idiom_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_idiom(
    idiom_id: uuid.UUID,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> None:
    idiom = _load(db, idiom_id)
    db.delete(idiom)  # cascade drops translations
    db.flush()
    idiom_runtime.reset_cache()


# ---------------------------------------------------------------------------
# Per-language translation endpoints
# ---------------------------------------------------------------------------


@router.put(
    "/{idiom_id}/translations/{language}",
    response_model=IdiomOut,
)
def upsert_translation(
    idiom_id: uuid.UUID,
    language: str,
    body: IdiomTranslationUpsert,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> IdiomOut:
    """Insert or replace the target-language equivalent for one idiom.
    Path parameter `language` wins over the body's language field if
    they disagree — treat the URL as authoritative."""
    idiom = _load(db, idiom_id)

    # Force path/body agreement so a caller can't accidentally overwrite
    # the wrong row via a mismatched body.
    lang = language.lower().strip()
    if body.language != lang:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"path language {lang!r} must match body language {body.language!r}",
        )

    existing = next(
        (t for t in idiom.translations if t.language == lang), None,
    )
    if existing is not None:
        existing.translation = body.translation
        existing.notes = body.notes
        existing.is_active = body.is_active
    else:
        db.add(IdiomTranslation(
            idiom_id=idiom.id,
            language=lang,
            translation=body.translation,
            notes=body.notes,
            is_active=body.is_active,
        ))
    db.flush()
    # Refresh the collection cache so the response reflects the write —
    # same identity-map trap the modules admin routes hit before.
    db.expire(idiom, ["translations"])
    idiom_runtime.reset_cache()
    return _serialize(_load(db, idiom_id))


@router.delete(
    "/{idiom_id}/translations/{language}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_translation(
    idiom_id: uuid.UUID,
    language: str,
    _admin: Annotated[User, Depends(require_super_admin)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> None:
    idiom = _load(db, idiom_id)
    lang = language.lower().strip()
    target = next((t for t in idiom.translations if t.language == lang), None)
    if target is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"no {lang!r} translation for this idiom",
        )
    db.delete(target)
    db.flush()
    idiom_runtime.reset_cache()
