"""
Pydantic request/response models for auth endpoints.

Kept separate from the general app/schemas.py so the auth surface can
evolve independently and so a reader immediately knows which fields are
user-provided (and therefore must be validated hard).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.config import settings


# Complexity: at least one letter and one digit. Deliberately not requiring
# special chars — modern NIST guidance is *length over complexity*, so the
# hard rule is length (settings.password_min_length) and this is a light
# floor to reject "12345678"-tier passwords.
_HAS_LETTER = re.compile(r"[A-Za-z]")
_HAS_DIGIT = re.compile(r"\d")


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, v: str) -> str:
        # Store lowercase — email is case-insensitive per RFC 5321 local-part
        # convention; anything else creates dup-account bugs (Bob@x.com vs
        # bob@x.com). trim whitespace as belt-and-suspenders.
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if len(v) < settings.password_min_length:
            raise ValueError(
                f"password must be at least {settings.password_min_length} characters"
            )
        if not _HAS_LETTER.search(v) or not _HAS_DIGIT.search(v):
            raise ValueError("password must contain at least one letter and one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime
