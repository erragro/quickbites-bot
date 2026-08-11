"""JWT create/decode — pure unit tests, no DB, no HTTP."""

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt as jose_jwt

from app.auth.jwt import InvalidToken, create_access_token, decode_access_token
from app.config import settings


def test_roundtrip_carries_subject():
    uid = uuid.uuid4()
    token = create_access_token(uid)
    claims = decode_access_token(token)
    assert claims["sub"] == str(uid)
    assert claims["type"] == "access"
    assert claims["iss"] == settings.jwt_issuer


def test_accepts_string_user_id():
    uid = str(uuid.uuid4())
    token = create_access_token(uid)
    assert decode_access_token(token)["sub"] == uid


def test_expired_token_rejected():
    # Craft a token whose exp is 1 second in the past.
    past = datetime.now(timezone.utc) - timedelta(seconds=1)
    payload = {
        "sub": str(uuid.uuid4()),
        "iat": int((past - timedelta(minutes=1)).timestamp()),
        "exp": int(past.timestamp()),
        "iss": settings.jwt_issuer,
        "type": "access",
    }
    token = jose_jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidToken):
        decode_access_token(token)


def test_tampered_signature_rejected():
    token = create_access_token(uuid.uuid4())
    # Flip a character in the signature portion.
    tampered = token[:-2] + ("XY" if token[-2:] != "XY" else "AB")
    with pytest.raises(InvalidToken):
        decode_access_token(tampered)


def test_wrong_issuer_rejected():
    payload = {
        "sub": str(uuid.uuid4()),
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "iss": "not-quickbites",
        "type": "access",
    }
    token = jose_jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidToken):
        decode_access_token(token)


def test_wrong_token_type_rejected():
    # Refresh-shaped token must not be accepted where access is required.
    payload = {
        "sub": str(uuid.uuid4()),
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "iss": settings.jwt_issuer,
        "type": "refresh",
    }
    token = jose_jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidToken):
        decode_access_token(token)


def test_missing_required_claim_rejected():
    # No `sub` — decoder demands it via options={"require": [...]}.
    payload = {
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
        "iss": settings.jwt_issuer,
        "type": "access",
    }
    token = jose_jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(InvalidToken):
        decode_access_token(token)
