"""Pydantic DTOs for the idiom-library admin API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# BCP-47 short codes we accept. Must stay in sync with the DB CHECK
# constraint on idiom_translations.language (migration 007) and the
# same whitelist used across fact_cards / complaint_templates / etc.
_LANGUAGES = frozenset({"en", "hi", "bn", "ta", "te", "kn", "mr"})

# Category taxonomy — matches the CHECK constraint on idiom_library.category
# (migration 007). Extending this requires both a DB migration relaxing
# the constraint AND updating this set.
_CATEGORIES = frozenset({"legal", "work", "money", "general", "safety"})


# ---------------------------------------------------------------------------
# Read shapes
# ---------------------------------------------------------------------------


class IdiomTranslationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    language: str
    translation: str
    notes: Optional[str] = None
    is_active: bool
    updated_at: datetime


class IdiomOut(BaseModel):
    """Full idiom row with its per-language translations embedded.
    The admin panel renders one card per idiom with the language grid
    inline; no need for a separate translations fetch."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_phrase: str
    meaning: str
    category: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
    translations: list[IdiomTranslationOut] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Write shapes
# ---------------------------------------------------------------------------


class IdiomTranslationUpsert(BaseModel):
    """One language's translation. Used both when creating an idiom
    (embedded in IdiomCreate.translations) and when updating a single
    language via PUT /idioms/{id}/translations/{lang}."""

    language: str
    translation: str = Field(..., min_length=1, max_length=2000)
    notes: Optional[str] = Field(default=None, max_length=1000)
    is_active: bool = True

    @field_validator("language")
    @classmethod
    def _lang_ok(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in _LANGUAGES:
            raise ValueError(
                f"language must be one of {sorted(_LANGUAGES)}"
            )
        return v


class IdiomCreate(BaseModel):
    source_phrase: str = Field(..., min_length=1, max_length=200)
    meaning: str = Field(..., min_length=1, max_length=1000)
    category: str
    is_active: bool = True
    # Optional bootstrap translations. Admins can also add these later
    # one at a time via the translations endpoints.
    translations: list[IdiomTranslationUpsert] = Field(default_factory=list)

    @field_validator("category")
    @classmethod
    def _cat_ok(cls, v: str) -> str:
        v = v.lower().strip()
        if v not in _CATEGORIES:
            raise ValueError(
                f"category must be one of {sorted(_CATEGORIES)}"
            )
        return v

    @field_validator("source_phrase")
    @classmethod
    def _phrase_ok(cls, v: str) -> str:
        # Store as-typed; the runtime scanner lowercases at match time.
        return v.strip()


class IdiomUpdate(BaseModel):
    """PATCH shape — every field optional so admins can toggle
    is_active without resending the rest."""

    source_phrase: Optional[str] = Field(default=None, min_length=1, max_length=200)
    meaning: Optional[str] = Field(default=None, min_length=1, max_length=1000)
    category: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("category")
    @classmethod
    def _cat_ok(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.lower().strip()
        if v not in _CATEGORIES:
            raise ValueError(
                f"category must be one of {sorted(_CATEGORIES)}"
            )
        return v
