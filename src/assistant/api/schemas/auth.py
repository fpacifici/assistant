"""Pydantic schemas for authentication endpoints."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    """Request body for POST /auth/register."""

    email: EmailStr
    password: str
    firstname: str
    lastname: str


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""

    email: EmailStr
    password: str


class UserResponse(BaseModel):
    """User profile returned after registration or from /auth/me."""

    uid: uuid.UUID
    email: str
    firstname: str
    lastname: str

    model_config = {"from_attributes": True}
