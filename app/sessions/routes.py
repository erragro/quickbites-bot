"""
User-facing sessions API — chat CRUD + send-message endpoint.

Endpoints (all authenticated):
  GET    /api/sessions                  list this user's sessions
  POST   /api/sessions                  start a new chat session
  GET    /api/sessions/{sid}            full transcript + turns
  PATCH  /api/sessions/{sid}            rename (update title)
  DELETE /api/sessions/{sid}            delete session and its turns
  POST   /api/sessions/{sid}/chat       send one message → bot response

Ownership: every route resolves the session by (session_id + current_user.id).
A session that exists but belongs to another user is treated as 404 — never
403 — so the endpoint isn't a probe for session-id existence.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth.dependencies import db_session_dep, get_current_active_user
from app.l1_cardinal.pipeline import run_turn
from app.models import ChatSession, Turn, User
from app.sessions.schemas import (
    ChatMessageRequest,
    ChatMessageResponse,
    SessionCreateRequest,
    SessionDetail,
    SessionRenameRequest,
    SessionSummary,
    TurnOut,
)


router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _new_session_id() -> str:
    """16-char hex, same shape as the runner-generated ids for continuity."""
    return secrets.token_hex(8)


def _load_owned_session(db: Session, session_id: str, user: User) -> ChatSession:
    """
    Ownership resolver. Anything that isn't owned by `user` becomes a 404 —
    including sessions that exist for someone else. That way the endpoint
    can't be used to check whether a session_id belongs to another user.
    """
    session = db.execute(
        select(ChatSession).where(
            ChatSession.session_id == session_id,
            ChatSession.user_id == user.id,
        )
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="session not found",
        )
    return session


@router.get("", response_model=list[SessionSummary])
def list_sessions(
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
    limit: int = 50,
    offset: int = 0,
) -> list[SessionSummary]:
    if limit < 1 or limit > 200:
        raise HTTPException(400, "limit must be between 1 and 200")
    if offset < 0:
        raise HTTPException(400, "offset must be >= 0")
    rows = db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user.id)
        .order_by(ChatSession.opened_at.desc())
        .limit(limit)
        .offset(offset)
    ).scalars().all()
    return [SessionSummary.model_validate(s) for s in rows]


@router.post("", response_model=SessionSummary, status_code=status.HTTP_201_CREATED)
def create_session(
    body: SessionCreateRequest,
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> SessionSummary:
    session = ChatSession(
        session_id=_new_session_id(),
        user_id=user.id,
        title=body.title,
        mode="chat",
    )
    db.add(session)
    db.flush()
    return SessionSummary.model_validate(session)


@router.get("/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> SessionDetail:
    session = _load_owned_session(db, session_id, user)
    turns = db.execute(
        select(Turn)
        .where(Turn.session_id == session_id)
        .order_by(Turn.id.asc())
    ).scalars().all()
    return SessionDetail(
        session_id=session.session_id,
        user_id=session.user_id,
        title=session.title,
        opened_at=session.opened_at,
        closed_at=session.closed_at,
        close_reason=session.close_reason,
        turns=[TurnOut.model_validate(t, from_attributes=True) for t in turns],
    )


@router.patch("/{session_id}", response_model=SessionSummary)
def rename_session(
    session_id: str,
    body: SessionRenameRequest,
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> SessionSummary:
    session = _load_owned_session(db, session_id, user)
    session.title = body.title
    db.flush()
    return SessionSummary.model_validate(session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: str,
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> None:
    session = _load_owned_session(db, session_id, user)
    # CASCADE on turns FK handles the transcript rows automatically.
    db.delete(session)
    db.flush()


@router.post("/{session_id}/chat", response_model=ChatMessageResponse)
def chat(
    session_id: str,
    body: ChatMessageRequest,
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> ChatMessageResponse:
    """
    Send a message from the authenticated user, run it through the Cardinal
    pipeline, return the bot's reply.

    Session must exist and be owned by the current user (or be brand-new
    with no turns yet — created via POST /api/sessions).
    """
    session = _load_owned_session(db, session_id, user)

    # Auto-title from the first message so the sidebar isn't full of "Untitled".
    if session.title is None:
        session.title = body.message[:50].strip() or "New chat"
        db.flush()

    result = run_turn(
        db,
        session_id=session_id,
        customer_message=body.message,
        mode="chat",
    )

    # run_turn's TurnResult doesn't carry turn_no; the persisted bot turn
    # is always the latest max, and it was written inside run_turn under the
    # same session db.
    latest_turn_no = db.execute(
        select(Turn.turn_no)
        .where(Turn.session_id == session_id, Turn.role == "bot")
        .order_by(Turn.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    detected_language = None
    if isinstance(result.classification, dict):
        detected_language = result.classification.get("detected_language")

    return ChatMessageResponse(
        session_id=session_id,
        turn_no=latest_turn_no or 0,
        bot_message=result.bot_message,
        actions=result.actions,
        detected_language=detected_language,
        route=result.route,
        escalation_group=result.escalation_group,
    )
