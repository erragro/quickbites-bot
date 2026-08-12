"""
Public chip-tap conversation endpoints — authenticated, user-scoped.

  GET  /api/chat/starters                  Full BU → issue-type tree
  POST /api/sessions/{sid}/select-issue    Persist chip selection + ack
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.auth.dependencies import db_session_dep, get_current_active_user
from app.conversation_studio.schemas import (
    BusinessUnitTree,
    ChatStartersResponse,
    IssueTypeChip,
    SelectIssueRequest,
    SelectIssueResponse,
)
from app.conversation_studio.service import (
    load_issue_type_full,
    pick_and_render_ack,
    resolve_data_points,
)
from app.models import BusinessUnit, ChatSession, IssueType, Turn, User
from app.sessions.routes import _load_owned_session


router = APIRouter(prefix="/api/chat", tags=["chat-starters"])


@router.get("/starters", response_model=ChatStartersResponse)
def get_starters(
    _user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> ChatStartersResponse:
    """
    Public chip tree the frontend renders on empty-chat state.
    Any authenticated user gets this — access-control is at the module
    level (chatbot module access), not the individual BU/issue type.
    """
    units = db.execute(
        select(BusinessUnit)
        .options(selectinload(BusinessUnit.issue_types))
        .where(
            BusinessUnit.is_active.is_(True),
            BusinessUnit.parent_id.is_(None),  # top-level only for now
        )
        .order_by(BusinessUnit.sort_order.asc(), BusinessUnit.name.asc())
    ).scalars().all()

    trees: list[BusinessUnitTree] = []
    for unit in units:
        # Filter + sort issue types in Python — the eager-load pulled
        # everything back, and there are ~3-4 per unit so it's trivial.
        chips = sorted(
            [it for it in unit.issue_types if it.is_active],
            key=lambda it: (it.sort_order, it.name),
        )
        # Skip empty categories — they render as blank sections in the
        # chip tree, which looks broken. If an admin creates a BU but
        # hasn't attached any issue types yet, hide it from the public
        # tree until they do.
        if not chips:
            continue
        trees.append(
            BusinessUnitTree(
                id=unit.id,
                code=unit.code,
                name=unit.name,
                icon=unit.icon,
                sort_order=unit.sort_order,
                issue_types=[IssueTypeChip.model_validate(c) for c in chips],
            )
        )
    return ChatStartersResponse(business_units=trees)


# Registered under the same prefix as /api/sessions so it lives with the
# rest of the session surface. Kept as a separate router file for tidiness.
issue_router = APIRouter(prefix="/api/sessions", tags=["chat-starters"])


@issue_router.post(
    "/{session_id}/select-issue",
    response_model=SelectIssueResponse,
)
def select_issue(
    session_id: str,
    body: SelectIssueRequest,
    user: Annotated[User, Depends(get_current_active_user)],
    db: Annotated[Session, Depends(db_session_dep)],
) -> SelectIssueResponse:
    """
    The chip-tap turn. Fast path — no LLM in the critical path:

    1. Load the customer's session (ownership check).
    2. Load the issue type + its data-point contract.
    3. Run declared fetchers → build enriched context dict.
    4. Persist issue_type_id + business_unit_id on the session so
       subsequent free-text turns know which contract is active.
    5. Pick a weighted-random ack template, render variables.
    6. Persist the ack as a bot turn so the transcript stays in sync
       with what the customer saw.
    7. Return the rendered ack + list of data points that actually
       resolved (frontend uses this to decide whether to prompt the
       customer for missing inputs like an order id).
    """
    session: ChatSession = _load_owned_session(db, session_id, user)

    issue_type: IssueType | None = load_issue_type_full(db, body.issue_type_id)
    if issue_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="issue type not found or inactive",
        )

    # Prefer the customer_id / order_id the caller supplied, then fall
    # back to whatever the session state already knew (from prior turns).
    order_id = body.order_id or session.known_order_id
    customer_id = body.customer_id or session.known_customer_id

    context, resolved_keys = resolve_data_points(
        db,
        issue_type,
        order_id=order_id,
        customer_id=customer_id,
    )

    # Persist selected issue type + BU on the session (source of truth
    # for later turns — Stage 1 can read this to skip re-classifying).
    session.issue_type_id = issue_type.id
    session.business_unit_id = issue_type.business_unit_id

    # Update the session's known-IDs if we resolved them from the request.
    if order_id and not session.known_order_id:
        session.known_order_id = order_id
    if customer_id and not session.known_customer_id:
        session.known_customer_id = customer_id

    # Set title from the issue-type name if empty — nicer sidebar rows.
    if not session.title:
        session.title = issue_type.name

    ack_text = pick_and_render_ack(db, issue_type.id, context)

    # Persist the ack turn. turn_no starts at 1; prior turns (from
    # explicit chat messages) may exist so we look up the max.
    last_turn = db.execute(
        select(Turn.turn_no)
        .where(Turn.session_id == session_id)
        .order_by(Turn.turn_no.desc())
        .limit(1)
    ).scalar_one_or_none()
    next_turn_no = (last_turn or 0) + 1

    db.add(
        Turn(
            session_id=session_id,
            turn_no=next_turn_no,
            role="bot",
            message=ack_text,
            classification={
                "source": "chip_tap",
                "issue_type_code": issue_type.code,
                "routes_to_intent": issue_type.routes_to_intent,
                "resolved_data_points": resolved_keys,
            },
            route="AUTO_RESOLVED",
        )
    )
    db.flush()

    return SelectIssueResponse(
        session_id=session_id,
        issue_type_id=issue_type.id,
        business_unit_id=issue_type.business_unit_id,
        acknowledgment=ack_text,
        resolved_data_points=resolved_keys,
    )
