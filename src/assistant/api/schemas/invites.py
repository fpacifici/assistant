"""Pydantic schemas for invite endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr

from assistant.models.schema import InviteState


class InviteCreate(BaseModel):
    """Request body for POST /invites."""

    invitee_email: EmailStr


class InviteResponse(BaseModel):
    """An invite, including its freshly-recomputed share URL."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invitee_email: str
    state: InviteState
    created_at: datetime
    expires_at: datetime
    url: str


class InvitePublicResponse(BaseModel):
    """Public (anonymous) validity check for an invite.

    Deliberately does not include the invitee's email — there is no email
    verification in this system yet, so leaking it here would let anyone
    holding the link register as that address without proving ownership of
    the inbox it was sent to. The registrant must type their own email on
    the accept-invite page; the backend still validates it matches the
    invite's invitee_email (see auth.service.register_user).
    """

    valid: bool


class InvitesConfigResponse(BaseModel):
    """Public config flags the frontend uses to gate registration UI."""

    registration_enabled: bool
    invites_enabled: bool
