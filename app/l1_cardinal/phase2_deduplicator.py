"""
Phase 2 Deduplicator — in-process SHA-256 cache keyed by (session_id, message).
If a customer repeats themselves within the TTL window, we replay the prior
bot reply instead of burning LLM tokens.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Optional

from app.config import settings


@dataclass
class CachedReply:
    bot_message: str
    actions: list[dict]
    stored_at: float


_cache: dict[str, CachedReply] = {}


def _key(session_id: str, message: str) -> str:
    h = hashlib.sha256()
    h.update(session_id.encode())
    h.update(b"\x00")
    h.update(message.strip().lower().encode())
    return h.hexdigest()


def lookup(session_id: str, message: str) -> Optional[CachedReply]:
    k = _key(session_id, message)
    entry = _cache.get(k)
    if not entry:
        return None
    if time.time() - entry.stored_at > settings.dedup_ttl_seconds:
        _cache.pop(k, None)
        return None
    return entry


def remember(session_id: str, message: str, bot_message: str, actions: list[dict]) -> None:
    k = _key(session_id, message)
    _cache[k] = CachedReply(
        bot_message=bot_message,
        actions=actions,
        stored_at=time.time(),
    )
