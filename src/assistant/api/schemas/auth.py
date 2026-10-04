"""Pydantic schemas for authentication endpoints."""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, EmailStr, Field


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
    auth_provider: Literal["password", "google"] = "password"

    model_config = {"from_attributes": True}


class GoogleSwapInfo(BaseModel):
    """Returned by GET /auth/google/swap — the account a pending swap converts."""

    email: str


class GoogleSwapRequest(BaseModel):
    """Request body for POST /auth/google/swap."""

    password: str


class GoogleReauthStart(BaseModel):
    """Returned by POST /auth/google/reauth — where to send the browser."""

    authorization_url: str


class SetPasswordRequest(BaseModel):
    """Request body for POST /auth/credentials/password."""

    password: str = Field(min_length=8)
