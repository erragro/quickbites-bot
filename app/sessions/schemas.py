"""Pydantic models for the user-facing /api/sessions and /api/chat surface."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SessionSummary(BaseModel):
    """One row in the sidebar list. Cheap to fetch — no turns joined."""

    model_config = ConfigDict(from_attributes=True)

    session_id: str
    title: Optional[str] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None


class SessionCreateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=200)


class SessionRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)


class TurnOut(BaseModel):
    turn_no: int
    role: str
    message: Optional[str] = None
    actions: Optional[list | dict] = None
    created_at: datetime


class SessionDetail(BaseModel):
    session_id: str
    user_id: Optional[uuid.UUID] = None
    title: Optional[str] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
    close_reason: Optional[str] = None
    turns: list[TurnOut]


class ChatMessageRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)


class ChatMessageResponse(BaseModel):
    session_id: str
    turn_no: int
    bot_message: str
    actions: list[dict[str, Any]] = Field(default_factory=list)
    detected_language: Optional[str] = None
    route: Optional[str] = None
    escalation_group: Optional[str] = None
