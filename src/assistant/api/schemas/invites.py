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
    """An invite. No link — invites are distributed by email only now."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    invitee_email: str
    state: InviteState
    created_at: datetime
    expires_at: datetime
    email_sent: bool | None = None
    """Set only by create/resend responses — whether that attempt's send
    succeeded. None on GET /invites (list), where there's no 'just
    attempted' outcome to report."""


class InvitePublicResponse(BaseModel):
    """Public (anonymous) validity check for an invite.

    Now includes the invitee's email, reversing the earlier deliberate
    omission — the reason it was omitted ('no email verification yet') no
    longer applies once the invite is delivered by emailing that address.
    Used by the accept-invite page to pre-fill (and lock) the email field.
    """

    valid: bool
    invitee_email: str | None = None


class InvitesConfigResponse(BaseModel):
    """Public config flags the frontend uses to gate registration UI."""

    registration_enabled: bool
    invites_enabled: bool
