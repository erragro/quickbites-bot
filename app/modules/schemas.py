"""Pydantic DTOs for the modules + admin API surface."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


AccessLevel = Literal["view", "edit", "admin"]


class ModuleOut(BaseModel):
    """Public shape — safe to return to any authenticated user."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    path: str
    is_system: bool
    sort_order: int


class ModuleWithAccess(ModuleOut):
    """Same as ModuleOut plus the current caller's access level (None = no
    access). Used by the frontend to render the module sidebar."""

    access_level: Optional[AccessLevel] = None


class ModuleCreate(BaseModel):
    key: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9_-]*$")
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=1000)
    icon: Optional[str] = Field(default=None, max_length=50)
    path: str = Field(..., min_length=1, max_length=100, pattern=r"^/[a-zA-Z0-9/_-]*$")
    sort_order: int = 100


class AccessGrant(BaseModel):
    module_id: uuid.UUID
    access_level: AccessLevel


class UserModuleAccessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    module_id: uuid.UUID
    module_key: str
    module_name: str
    access_level: AccessLevel
    granted_at: datetime
    granted_by: Optional[uuid.UUID] = None


class UserAdminOut(BaseModel):
    """Admin-panel view of a user + all their module accesses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    is_active: bool
    is_super_admin: bool
    created_at: datetime
    module_accesses: list[UserModuleAccessOut] = Field(default_factory=list)


class UserAdminUpdate(BaseModel):
    """PATCH body — every field optional."""

    is_active: Optional[bool] = None
    is_super_admin: Optional[bool] = None
