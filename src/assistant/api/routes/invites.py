"""Invite API routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response

from assistant.api.dependencies import CurrentUser, SessionDep
from assistant.api.schemas.invites import (
    InviteCreate,
    InvitePublicResponse,
    InviteResponse,
    InvitesConfigResponse,
)
from assistant.config import Config
from assistant.invites.exceptions import InviteNotUsableError, InvitesDisabledError
from assistant.invites.service import (
    build_invite_url,
    create_invite,
    get_valid_pending_invite,
    list_invites_for_user,
    void_invite,
)
from assistant.models.schema import Invite, InviteState

router = APIRouter()


def _invite_response(invite: Invite, config: Config) -> InviteResponse:
    return InviteResponse(
        id=invite.id,
        invitee_email=invite.invitee_email,
        state=InviteState(invite.state),
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        url=build_invite_url(invite.id, config),
    )


@router.get("/config", response_model=InvitesConfigResponse)
def get_invites_config() -> InvitesConfigResponse:
    config = Config().get_registration_config()
    return InvitesConfigResponse(
        registration_enabled=config["registration_enabled"],
        invites_enabled=config["invites_enabled"],
    )


@router.get("/{invite_id}/public", response_model=InvitePublicResponse)
def get_invite_public(invite_id: uuid.UUID, session: SessionDep) -> InvitePublicResponse:
    config = Config().get_registration_config()
    try:
        get_valid_pending_invite(session, invite_id, config)
    except (InviteNotUsableError, InvitesDisabledError):
        return InvitePublicResponse(valid=False)
    return InvitePublicResponse(valid=True)


@router.post("", status_code=201, response_model=InviteResponse)
def create_invite_endpoint(
    body: InviteCreate,
    session: SessionDep,
    user: CurrentUser,
) -> InviteResponse:
    config = Config()
    invite = create_invite(
        session, user, body.invitee_email, config.get_registration_config()
    )
    return _invite_response(invite, config)


@router.get("", response_model=list[InviteResponse])
def list_invites_endpoint(
    session: SessionDep,
    user: CurrentUser,
) -> list[InviteResponse]:
    config = Config()
    invites = list_invites_for_user(session, user)
    return [_invite_response(invite, config) for invite in invites]


@router.delete("/{invite_id}", status_code=204)
def void_invite_endpoint(
    invite_id: uuid.UUID,
    session: SessionDep,
    user: CurrentUser,
) -> Response:
    void_invite(session, user, invite_id)
    return Response(status_code=204)
