"""Pydantic schemas for User endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    email: str
    firstname: str
    lastname: str
    invite_quota: int | None = None
    invite_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    email: str | None = None
    firstname: str | None = None
    lastname: str | None = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    uid: uuid.UUID
    email: str
    firstname: str
    lastname: str
    invite_quota_remaining: int
