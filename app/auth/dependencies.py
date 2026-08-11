"""
FastAPI dependencies for auth.

`get_current_user` is the star: attach it to any route as
`user: User = Depends(get_current_user)` to require a valid JWT and get the
loaded user row. Rejection is always 401 with a WWW-Authenticate header so
clients know to prompt for login.

`get_current_active_user` additionally enforces the is_active flag — use
this for any route that mutates state or performs money-adjacent work.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Iterator

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.jwt import InvalidToken, decode_access_token
from app.db import SessionLocal
from app.models import User


# tokenUrl only affects OpenAPI docs; the actual login route is /auth/login.
_oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def db_session_dep() -> Iterator[Session]:
    """DB session per request. Rolled back on exception, closed always."""
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def _unauthorized(detail: str = "not authenticated") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    token: Annotated[str | None, Depends(_oauth2_scheme)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> User:
    if not token:
        raise _unauthorized("missing bearer token")
    try:
        claims = decode_access_token(token)
    except InvalidToken:
        raise _unauthorized("invalid or expired token")

    try:
        user_id = uuid.UUID(claims["sub"])
    except (KeyError, ValueError):
        raise _unauthorized("token subject is not a valid user id")

    user = db.execute(
        select(User).where(User.id == user_id)
    ).scalar_one_or_none()
    if user is None:
        # Token references a user that no longer exists (deleted account).
        raise _unauthorized("user not found")
    return user


def get_current_active_user(
    user: Annotated[User, Depends(get_current_user)],
) -> User:
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="user account is disabled",
        )
    return user
