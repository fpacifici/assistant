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
    invite_id: uuid.UUID | None = None


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""

    email: EmailStr
    password: str


class RegisterResponse(BaseModel):
    """Returned by POST /auth/register — registration no longer auto-logs-in."""

    email: str
    confirmation_email_sent: bool


class ConfirmationRequest(BaseModel):
    """Request body for POST /auth/resend-confirmation."""

    email: EmailStr


class UserResponse(BaseModel):
    """User profile returned after registration or from /auth/me."""

    uid: uuid.UUID
    email: str
    firstname: str
    lastname: str
    invite_quota_remaining: int

    model_config = {"from_attributes": True}
