"""
JWT access tokens — HS256, short claim set.

Claims:
  sub  → user_id (uuid as string)
  exp  → expiry (unix seconds)
  iat  → issued-at (unix seconds)
  iss  → configured issuer
  type → "access"    (space for a future "refresh" token type)

Rejection is silent (returns None) — the caller renders 401. Never leak
which claim failed to the client.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from app.config import settings


class InvalidToken(Exception):
    """Raised when a token fails validation. Caller should render 401."""


def create_access_token(user_id: uuid.UUID | str, *, extra: Optional[dict] = None) -> str:
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_access_ttl_minutes)
    payload: dict = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": settings.jwt_issuer,
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """
    Decode + validate an access token. Raises InvalidToken on any failure
    (bad signature, expired, wrong issuer, wrong type). Returns the claims
    dict on success.
    """
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "iss"]},
        )
    except JWTError as exc:
        raise InvalidToken(str(exc)) from exc

    # python-jose's `options={"require": [...]}` only reliably enforces `exp`.
    # Explicit belt-and-suspenders check for the other claims we depend on —
    # a missing `sub` would otherwise crash downstream instead of returning 401.
    for required in ("sub", "iat", "iss"):
        if required not in claims:
            raise InvalidToken(f"missing required claim: {required}")

    if claims.get("type") != "access":
        raise InvalidToken("wrong token type")
    return claims
