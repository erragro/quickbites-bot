"""
Password hashing — bcrypt at cost 12.

Called directly by the signup/login routes; kept in its own module so the
hashing choice can be swapped (argon2, scrypt) without touching route code.
Constant-time comparison lives inside bcrypt.checkpw — never write a manual
`==` comparison against stored hashes.
"""

from __future__ import annotations

import bcrypt

_ROUNDS = 12  # ~250ms per hash on typical hardware — good OWASP-recommended cost


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the password, decoded to a UTF-8 str for storage."""
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    salt = bcrypt.gensalt(rounds=_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time verify. Returns False on any input error (never raises to
    the caller) so route code can treat every non-True return as auth-failed."""
    if not password or not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Corrupted or wrong-format hash → treat as bad credentials, not 500.
        return False
