"""Password hashing — pure unit tests, no DB."""

import pytest

from app.auth.password import hash_password, verify_password


def test_hash_verify_roundtrip():
    h = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", h) is True


def test_verify_rejects_wrong_password():
    h = hash_password("password1")
    assert verify_password("password2", h) is False


def test_verify_is_case_sensitive():
    h = hash_password("Password1")
    assert verify_password("password1", h) is False


def test_hash_produces_different_output_each_call():
    # Salt should differ per call → same input, different hash. Both verify.
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2
    assert verify_password("same", h1) is True
    assert verify_password("same", h2) is True


def test_hash_rejects_empty_string():
    with pytest.raises(ValueError):
        hash_password("")


def test_verify_returns_false_for_empty_inputs():
    # Route code depends on this: any missing input == auth failed, never crash.
    assert verify_password("", "anything") is False
    assert verify_password("password1", "") is False
    assert verify_password("", "") is False


def test_verify_returns_false_for_corrupted_hash():
    # Not a valid bcrypt-shaped string → treat as bad credentials, not 500.
    assert verify_password("password1", "not-a-bcrypt-hash") is False
