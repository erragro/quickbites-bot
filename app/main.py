from __future__ import annotations

import logging
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app import simulator_client
from app.auth.dependencies import get_current_active_user
from app.auth.routes import limiter as auth_limiter, router as auth_router
from app.config import settings
from app.db import db_session, engine
from app.migrations import bootstrap
from app.models import User
from app.runners import dev_runner, prod_runner
from app.runners.session_runner import SessionSummary
from app.contracts.routes import router as contracts_router
from app.conversation_studio.admin_routes import (
    router as conversation_admin_router,
)
from app.idioms.admin_routes import router as idioms_admin_router
from app.conversation_studio.routes import (
    issue_router as chat_issue_router,
    router as chat_starters_router,
)
from app.modules.admin_routes import router as admin_router
from app.modules.routes import router as modules_router
from app.sessions.routes import router as sessions_router


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="QuickBites Support Bot",
    version="0.1.0",
    description="Cardinal-inspired synchronous 5-phase + 4-stage LLM pipeline.",
)

# slowapi wiring — one shared Limiter is defined in app.auth.routes and
# reused here so every rate-limited endpoint uses the same key function
# and storage. The exception handler returns 429 JSON.
app.state.limiter = auth_limiter
app.add_exception_handler(
    RateLimitExceeded,
    lambda request, exc: JSONResponse(
        status_code=429,
        content={"detail": f"rate limit exceeded: {exc.detail}"},
    ),
)

app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(chat_starters_router)
app.include_router(chat_issue_router)
app.include_router(conversation_admin_router)
app.include_router(contracts_router)
app.include_router(idioms_admin_router)
app.include_router(modules_router)
app.include_router(admin_router)


_UNSAFE_JWT_DEFAULT = "CHANGE_ME_IN_PRODUCTION_this_default_is_unsafe"


@app.on_event("startup")
def _startup() -> None:
    # Guard against shipping the default JWT secret to any non-dev env.
    # ENV var `APP_ENV` is set by the container manifest; local runs leave
    # it unset and we tolerate the default (with a loud warning).
    env = os.getenv("APP_ENV", "local")
    if settings.jwt_secret == _UNSAFE_JWT_DEFAULT:
        if env != "local":
            raise RuntimeError(
                f"refusing to boot in APP_ENV={env} with the default JWT secret; "
                "set the JWT_SECRET env var (Secret Manager in prod)."
            )
        logger.warning("using default JWT secret — safe for local dev only")

    try:
        loaded = bootstrap.run()
        logger.info("bootstrap %s", loaded)
    except Exception:
        logger.exception("bootstrap failed — service will serve /ping but runs will error")


@app.get("/ping")
def ping() -> dict:
    """Liveness endpoint. NOT named /healthz — Google Cloud Run's frontend
    silently intercepts /healthz, /health, /livez and returns its own 404
    before the request reaches the container."""
    return {"status": "ok"}


@app.get("/healthz")
def healthz() -> dict:
    """Backwards-compat alias kept for local docker-compose runs. On Cloud Run
    this route is shadowed by Google's frontend (see /ping)."""
    return {"status": "ok"}


class RunDevBody(BaseModel):
    scenario_id: Optional[int] = None


# The /run/* endpoints below drive the *simulator* — they're the internal
# playback/eval surface, not the user-facing chat. They are auth-guarded so
# only an authenticated user can burn quota against the hosted simulator.
# User-facing chat lives under /api/sessions/{sid}/chat.


@app.post("/run/dev")
def run_dev(
    body: RunDevBody,
    _user: User = Depends(get_current_active_user),
) -> SessionSummary:
    if body.scenario_id is not None and body.scenario_id not in (101, 102, 103, 104, 105):
        raise HTTPException(400, "scenario_id must be 101-105 or omitted")
    return dev_runner.run_dev(body.scenario_id)


@app.post("/run/dev/all")
def run_dev_all(
    _user: User = Depends(get_current_active_user),
) -> list[SessionSummary]:
    return dev_runner.run_all_rehearsal()


@app.post("/run/prod")
def run_prod(
    _user: User = Depends(get_current_active_user),
) -> dict:
    results = prod_runner.run_prod_all()
    return {
        "sessions_run": len(results),
        "summaries": [s for s in results],
    }


# NOTE: the old anonymous /sessions and /sessions/{id} routes were removed —
# they returned every session across every user with no ownership check.
# Use /api/sessions and /api/sessions/{sid} (both authenticated + user-scoped)
# from the sessions router instead.


@app.get("/score")
def score() -> dict:
    return simulator_client.candidate_summary()


@app.get("/simulator/healthz")
def simulator_healthz() -> dict:
    return simulator_client.healthz()
