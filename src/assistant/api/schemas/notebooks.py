"""Pydantic schemas for Notebook endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from assistant.models.schema import Entitlement, PermissionName, RoleName


class NotebookCreate(BaseModel):
    name: str


class NotebookUpdate(BaseModel):
    name: str | None = None


class NotebookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    owner_id: uuid.UUID
    permissions: list[PermissionName]


class EntitlementCreate(BaseModel):
    email: str
    role: RoleName


class EntitlementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    principal_id: uuid.UUID
    principal_email: str
    role: RoleName
    created_at: datetime

    @classmethod
    def from_entitlement(cls, entitlement: Entitlement) -> EntitlementResponse:
        return cls(
            id=entitlement.id,
            principal_id=entitlement.principal_id,
            principal_email=entitlement.principal.email,
            role=RoleName(entitlement.role_name),
            created_at=entitlement.created_at,
        )
