"""Invites service — creation, validation, and lifecycle of Invites."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from assistant.config import Config
from assistant.invites.exceptions import (
    InviteEmailMismatchError,
    InviteNotUsableError,
    InvitePermissionError,
    InvitesDisabledError,
    QuotaExhaustedError,
    RegistrationDisabledError,
)
from assistant.models.schema import Invite, InviteState, User

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from assistant.config import RegistrationConfig


def build_invite_url(invite_id: uuid.UUID, config: Config) -> str:
    """Return the invite's share URL, recomputed fresh on every call.

    Never stored. Depends on config.public_origin() (raises if domain is
    unset, same as the email service).
    """
    return f"{config.public_origin()}/invite/{invite_id}"


def list_invites_for_user(session: Session, user: User) -> list[Invite]:
    """Return every invite sent by user, pending and historical."""
    stmt = select(Invite).where(Invite.inviter_id == user.uid)
    return list(session.scalars(stmt))


def default_quota_for_new_user(config: RegistrationConfig, override: int | None) -> int:
    """Return override if given, else config's default_quota."""
    return override if override is not None else config["default_quota"]


# --- Creation ---


def create_invite(
    session: Session,
    inviter: User,
    invitee_email: str,
    config: RegistrationConfig,
) -> Invite:
    """Create a new pending invite, consuming one unit of the inviter's quota.

    Raises InvitesDisabledError if invites_enabled is false.
    Raises QuotaExhaustedError if inviter.invite_quota_remaining <= 0.
    Always creates a new row — re-inviting an already-pending email is
    never idempotent (the recipient may have lost the original link).
    Does NOT check whether invitee_email already has a User — an invite to
    an already-registered address is harmless (it will simply never
    convert; nothing surfaces it as an error).
    """
    if not config["invites_enabled"]:
        raise InvitesDisabledError
    if inviter.invite_quota_remaining <= 0:
        raise QuotaExhaustedError
    inviter.invite_quota_remaining -= 1
    return _create_invite_row(
        session, inviter, invitee_email, config, quota_consumed=True
    )


def admin_create_invite(
    session: Session,
    inviter: User,
    invitee_email: str,
    config: RegistrationConfig,
) -> Invite:
    """Same as create_invite but bypasses invites_enabled AND quota entirely.

    Sets quota_consumed=False — CLI-issued invites cannot be disabled, per
    spec.
    """
    return _create_invite_row(
        session, inviter, invitee_email, config, quota_consumed=False
    )


def _create_invite_row(
    session: Session,
    inviter: User,
    invitee_email: str,
    config: RegistrationConfig,
    *,
    quota_consumed: bool,
) -> Invite:
    invite = Invite(
        invitee_email=invitee_email,
        inviter_id=inviter.uid,
        state=InviteState.PENDING.value,
        quota_consumed=quota_consumed,
        expires_at=datetime.now(UTC) + timedelta(days=config["expiry_days"]),
    )
    session.add(invite)
    session.flush()
    return invite


# --- Validation ---


def get_valid_pending_invite(
    session: Session,
    invite_id: uuid.UUID,
    config: RegistrationConfig,
) -> Invite:
    """Return the invite if pending and unexpired.

    Raises InvitesDisabledError if invites_enabled is false (kill switch
    covers redemption too). Raises InviteNotUsableError if the id doesn't
    exist, isn't PENDING, or now() > expires_at.
    """
    if not config["invites_enabled"]:
        raise InvitesDisabledError
    invite = session.get(Invite, invite_id)
    if invite is None or invite.state != InviteState.PENDING.value:
        raise InviteNotUsableError
    if invite.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise InviteNotUsableError
    return invite


def resolve_registration_gate(
    session: Session,
    config: RegistrationConfig,
    email: str,
    invite_id: uuid.UUID | None,
) -> Invite | None:
    """Enforce the registration_enabled/invites_enabled gate.

    Shared by every path that mints a User directly from caller-supplied
    identity (self-registration, invite acceptance, and CLI/HTTP user
    creation via POST /user) — none of them may bypass the gate just
    because they aren't the register endpoint.

    Returns the validated Invite when invite_id is given (raising
    InviteEmailMismatchError if its invitee_email doesn't match email,
    or whatever get_valid_pending_invite raises for an unusable one).
    Raises RegistrationDisabledError if registration_enabled is false
    and no invite_id was given.
    """
    if invite_id is not None:
        invite = get_valid_pending_invite(session, invite_id, config)
        if invite.invitee_email.lower() != email.lower():
            raise InviteEmailMismatchError(invite_id)
        return invite
    if not config["registration_enabled"]:
        raise RegistrationDisabledError
    return None


# --- Lifecycle transitions ---


def convert_invite(session: Session, invite_id: uuid.UUID) -> None:
    """Mark PENDING -> CONVERTED. No quota refund — this is a successful spend."""
    invite = session.get(Invite, invite_id)
    if invite is None:
        return
    invite.state = InviteState.CONVERTED.value
    session.flush()


def _refund_if_consumed(session: Session, invite: Invite) -> None:
    if invite.quota_consumed:
        inviter = session.get(User, invite.inviter_id)
        if inviter is not None:
            inviter.invite_quota_remaining += 1


def void_invite(session: Session, actor: User, invite_id: uuid.UUID) -> None:
    """Sender-initiated void.

    Raises InvitePermissionError if actor is not the invite's inviter.
    No-ops (does not raise) if already non-pending. Refunds quota iff
    quota_consumed.
    """
    invite = session.get(Invite, invite_id)
    if invite is None:
        return
    if invite.inviter_id != actor.uid:
        raise InvitePermissionError
    if invite.state != InviteState.PENDING.value:
        return
    invite.state = InviteState.VOID.value
    _refund_if_consumed(session, invite)
    session.flush()


def admin_void_invite(session: Session, invite_id: uuid.UUID) -> None:
    """Force-void regardless of sender. Same refund rule as void_invite."""
    invite = session.get(Invite, invite_id)
    if invite is None:
        return
    if invite.state != InviteState.PENDING.value:
        return
    invite.state = InviteState.VOID.value
    _refund_if_consumed(session, invite)
    session.flush()


def delete_invite(session: Session, invite_id: uuid.UUID) -> None:
    """Permanently remove an Invite row — admin-only erasure.

    Distinct from void (a lifecycle transition that keeps the row for the
    sender's history). No-ops if the id doesn't exist.

    If the invite is still PENDING and quota_consumed, refunds the
    inviter's quota first — otherwise a still-live invite could be erased
    out from under its sender, leaving them down a quota point with no row
    left to explain why or to void for the refund.
    """
    invite = session.get(Invite, invite_id)
    if invite is None:
        return
    if invite.state == InviteState.PENDING.value:
        _refund_if_consumed(session, invite)
    session.delete(invite)
    session.flush()


def replenish_quota(session: Session, user: User, amount: int) -> None:
    """Add amount to user.invite_quota_remaining.

    Adds a delta, never sets an absolute value — an admin blind-replenishing
    can't accidentally lower someone's quota by not checking their current
    balance first.
    """
    user.invite_quota_remaining += amount
    session.flush()


# --- Gated user creation ---


def create_gated_user(  # noqa: PLR0913
    session: Session,
    *,
    email: str,
    firstname: str,
    lastname: str,
    invite_id: uuid.UUID | None,
    invite_quota_override: int | None = None,
) -> tuple[User, Invite | None]:
    """Create a User row after enforcing the registration/invite gate.

    Shared by every path that mints a User from caller-supplied identity
    — password registration, direct POST /user, Google sign-up — so the
    gate check, quota assignment, and on_user_created cascade live in
    exactly one place. Does NOT create a Credential; callers own that
    (a password hash, a google provider_subject, or nothing at all for
    the generic POST /user path) since it's the one part that actually
    differs per caller.

    Returns (user, invite) so a caller that needs invite.id (none do
    today — on_user_created already takes invite.id if invite else None
    internally) or wants to branch on whether an invite was used can;
    most callers only look at the User.

    Raises RegistrationDisabledError / InvitesDisabledError /
    InviteNotUsableError / InviteEmailMismatchError per
    resolve_registration_gate — uncaught, same as today.
    """
    config = Config().get_registration_config()
    invite = resolve_registration_gate(session, config, email, invite_id)
    user = User(
        email=email,
        firstname=firstname,
        lastname=lastname,
        invite_quota_remaining=default_quota_for_new_user(config, invite_quota_override),
    )
    session.add(user)
    session.flush()
    on_user_created(session, user, used_invite_id=invite.id if invite else None)
    return user, invite


def on_user_created(
    session: Session,
    user: User,
    *,
    used_invite_id: uuid.UUID | None = None,
) -> None:
    """Called by every user-creation path after the User row is flushed.

    If used_invite_id is given, converts that specific invite. Then, for
    ALL other PENDING invites addressed to user.email (case-insensitive,
    any sender), voids and refunds each — the one shared implementation of
    "any account creation for this email kills every other pending invite
    for it".
    """
    if used_invite_id is not None:
        convert_invite(session, used_invite_id)

    stmt = select(Invite).where(
        Invite.state == InviteState.PENDING.value,
        Invite.invitee_email.ilike(user.email),
    )
    for invite in session.scalars(stmt):
        if invite.id == used_invite_id:
            continue
        invite.state = InviteState.VOID.value
        _refund_if_consumed(session, invite)
    session.flush()
