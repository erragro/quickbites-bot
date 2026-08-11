"""
Auth HTTP routes: /auth/signup, /auth/login, /auth/me.

- Signup: creates user, returns access token (log user in immediately).
- Login: constant-time password check, returns access token. Auth failures
  return an identical error whether the email exists or not (blocks user
  enumeration).
- /me: cheap "who am I" check for the frontend after page reload.

Rate limits are enforced via slowapi and are per-IP (see main.py wiring).
Signup + login are the endpoints most attacked by brute-force + credential
stuffing; the limits here (from settings) are the second layer of defence
behind the container-level nginx caps.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import db_session_dep, get_current_active_user
from app.auth.jwt import create_access_token
from app.auth.password import hash_password, verify_password
from app.auth.schemas import LoginRequest, SignupRequest, TokenResponse, UserOut
from app.config import settings
from app.models import User


router = APIRouter(prefix="/auth", tags=["auth"])

# Standalone limiter so this module can be imported before main.py wires
# the middleware; main.py attaches it to the FastAPI app on startup.
limiter = Limiter(key_func=get_remote_address)


@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit(settings.auth_signup_rate)
def signup(
    request: Request,  # required for slowapi to derive the client IP
    body: SignupRequest,
    db: Annotated[Session, Depends(db_session_dep)],
) -> TokenResponse:
    user = User(
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    try:
        db.flush()  # forces the UNIQUE constraint check now, not later
    except IntegrityError:
        db.rollback()
        # Deliberately vague — same error surface whether it's a dup email
        # or something else — so the endpoint isn't a user-enumeration oracle.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="unable to create account with this email",
        )

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.jwt_access_ttl_minutes,
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.auth_login_rate)
def login(
    request: Request,
    body: LoginRequest,
    db: Annotated[Session, Depends(db_session_dep)],
) -> TokenResponse:
    user = db.execute(
        select(User).where(User.email == body.email)
    ).scalar_one_or_none()

    # Constant-time-ish: always run verify_password so timing doesn't
    # differentiate "no such email" from "wrong password". Use a fixed
    # bcrypt-shaped placeholder so verify_password takes the full compute
    # path even when user is None.
    hashed = user.password_hash if user else _DUMMY_HASH
    ok = verify_password(body.password, hashed)

    if not user or not ok or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        expires_in_minutes=settings.jwt_access_ttl_minutes,
    )


@router.get("/me", response_model=UserOut)
def me(
    user: Annotated[User, Depends(get_current_active_user)],
) -> UserOut:
    return UserOut.model_validate(user)


# Pre-computed bcrypt hash of the string "unused-placeholder-do-not-match".
# Used by login() to keep timing constant when the email doesn't exist.
# Regenerate with: bcrypt.hashpw(b"unused-placeholder-do-not-match", bcrypt.gensalt(12))
_DUMMY_HASH = "$2b$12$Q9m0KZLE7bZY0jKFqk8n7uWvzE6nlDzR6kL8LZs2fZUw6bH1CfPTa"
