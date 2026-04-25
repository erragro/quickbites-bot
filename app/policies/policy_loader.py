from __future__ import annotations

from functools import lru_cache

from app.config import POLICY_FAQ_PATH


@lru_cache(maxsize=1)
def policy_text() -> str:
    return POLICY_FAQ_PATH.read_text(encoding="utf-8")
