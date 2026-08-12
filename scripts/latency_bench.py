"""
End-to-end latency benchmark for the chat pipeline.

Runs N conversations of M turns each, records wall-clock time per HTTP call
and reads the persisted stage_timings_ms JSON from the turns table. Prints
p50/p95/max per stage and per-turn.

Usage:
    .venv/bin/python scripts/latency_bench.py [--conversations N] [--warmup 1]
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
import uuid
from typing import Any

import httpx
from sqlalchemy import text

from app.db import SessionLocal


BASE = "http://localhost:8000"

# Two-turn conversation: T1 asks the customer for their order (matrix
# is blocked without an order); T2 provides the order, matrix fires, we
# get a refund + complaint. Realistic + exercises every stage.
TURNS = [
    "Hi, my food just arrived and it was completely cold. Really disappointing.",
    "It's order #452 from Express Pizza. Please help.",
]


def _signup(client: httpx.Client) -> str:
    email = f"bench-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post(
        f"{BASE}/auth/signup",
        json={"email": email, "password": "password1"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _create_session(client: httpx.Client, token: str) -> str:
    r = client.post(
        f"{BASE}/api/sessions",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "bench"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["session_id"]


def _send_chat(client: httpx.Client, token: str, sid: str, msg: str) -> float:
    """Returns wall-clock seconds for the HTTP round-trip."""
    t0 = time.perf_counter()
    r = client.post(
        f"{BASE}/api/sessions/{sid}/chat",
        headers={"Authorization": f"Bearer {token}"},
        json={"message": msg},
        timeout=120,
    )
    r.raise_for_status()
    return time.perf_counter() - t0


def _cleanup(client: httpx.Client, token: str, sid: str) -> None:
    client.delete(
        f"{BASE}/api/sessions/{sid}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )


def _stage_timings_for(session_ids: list[str]) -> list[dict[str, int]]:
    """Pull the persisted stage_timings_ms for every bot turn in the given sessions."""
    if not session_ids:
        return []
    with SessionLocal() as db:
        rows = db.execute(
            text(
                "SELECT stage_timings_ms FROM turns "
                "WHERE session_id = ANY(:sids) AND role='bot' AND stage_timings_ms IS NOT NULL "
                "ORDER BY session_id, turn_no"
            ),
            {"sids": session_ids},
        ).all()
    out: list[dict[str, int]] = []
    for (raw,) in rows:
        if isinstance(raw, dict):
            out.append(raw)
        elif isinstance(raw, str):
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                pass
    return out


def _summarize(name: str, values: list[float]) -> str:
    if not values:
        return f"  {name:32s} (no data)"
    values_sorted = sorted(values)
    n = len(values_sorted)
    p50 = values_sorted[n // 2]
    p95 = values_sorted[min(n - 1, int(n * 0.95))]
    return (
        f"  {name:32s}  "
        f"n={n:3d}  "
        f"min={min(values_sorted):7.1f}  "
        f"p50={p50:7.1f}  "
        f"p95={p95:7.1f}  "
        f"max={max(values_sorted):7.1f}  "
        f"mean={statistics.mean(values_sorted):7.1f}"
    )


def run(conversations: int, warmup: int) -> None:
    client = httpx.Client()
    token = _signup(client)

    print(f"warm-up: {warmup} conversation(s)")
    for _ in range(warmup):
        sid = _create_session(client, token)
        for msg in TURNS:
            _send_chat(client, token, sid, msg)
        _cleanup(client, token, sid)

    per_turn_wall: dict[int, list[float]] = {i: [] for i in range(len(TURNS))}
    session_ids: list[str] = []

    print(f"\nrunning {conversations} conversations × {len(TURNS)} turns each")
    for c in range(conversations):
        sid = _create_session(client, token)
        session_ids.append(sid)
        for i, msg in enumerate(TURNS):
            dt = _send_chat(client, token, sid, msg)
            per_turn_wall[i].append(dt * 1000)  # convert to ms
        print(f"  conversation {c+1}/{conversations} done")

    # Give the DB a moment to be consistent
    time.sleep(0.5)
    stage_timings = _stage_timings_for(session_ids)

    print("\n=== HTTP wall-clock per turn (ms) ===")
    for i in range(len(TURNS)):
        print(_summarize(f"turn {i+1} (HTTP)", per_turn_wall[i]))

    # Aggregate stage timings across all turns
    if stage_timings:
        print("\n=== per-stage timings from turns.stage_timings_ms (ms) ===")
        keys = sorted({k for t in stage_timings for k in t.keys()})
        for k in keys:
            vals = [float(t[k]) for t in stage_timings if k in t]
            print(_summarize(k, vals))

    total_ms = [sum(w) for w in zip(*per_turn_wall.values())]
    print(f"\n=== full-conversation ({len(TURNS)} turns) HTTP wall-clock (ms) ===")
    print(_summarize("total per conversation", total_ms))

    # Cleanup benchmark sessions
    for sid in session_ids:
        try:
            _cleanup(client, token, sid)
        except Exception:  # noqa: BLE001
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conversations", type=int, default=5)
    ap.add_argument("--warmup", type=int, default=1)
    args = ap.parse_args()
    run(args.conversations, args.warmup)


if __name__ == "__main__":
    main()
