"""Invites module exceptions."""

from __future__ import annotations


class InvitesError(Exception):
    """Base exception for the invites module."""


class InviteNotUsableError(InvitesError):
    """Invite doesn't exist, isn't pending, or is past its expiry.

    Maps to the one generic "no longer valid" response — never
    distinguishes which of those three is true, to avoid leaking whether
    an account already exists for the invited address.
    """


class InviteEmailMismatchError(InvitesError):
    """Submitted registration email doesn't match the invite's invitee_email."""


class InvitesDisabledError(InvitesError):
    """invites_enabled=false: creating or redeeming any invite is rejected."""


class RegistrationDisabledError(InvitesError):
    """registration_enabled=false and no (valid) invite_id was supplied."""


class QuotaExhaustedError(InvitesError):
    """Sender has no invite_quota_remaining."""


class InvitePermissionError(InvitesError):
    """Caller tried to void an invite they didn't send (and isn't admin)."""
