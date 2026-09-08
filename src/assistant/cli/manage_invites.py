"""Admin CLI for managing invites and invite quotas.

Direct-DB-session script, same shape as add_evernote.py/setup_database.py —
authorized purely by shell access to run it. There is no in-app admin role
or HTTP-reachable admin identity to authenticate as (see docs/specs/0005-invites.md).
"""

from __future__ import annotations

import argparse
import sys
import uuid

from assistant.config import Config
from assistant.invites.service import (
    admin_create_invite,
    admin_void_invite,
    delete_invite,
    replenish_quota,
)
from assistant.models.database import get_session_factory
from assistant.models.schema import Invite, User
from assistant.notes.user_service import get_user_by_email


def cmd_create(args: argparse.Namespace) -> None:
    config = Config().get_registration_config()
    session_factory = get_session_factory()
    with session_factory() as session:
        sender = get_user_by_email(session, args.sender_email)
        invite = admin_create_invite(session, sender, args.invitee_email, config)
        session.commit()
        print(  # noqa: T201
            f"Created invite {invite.id} for {args.invitee_email} "
            f"(as {args.sender_email}, quota not consumed)"
        )


def cmd_void(args: argparse.Namespace) -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        admin_void_invite(session, args.invite_id)
        session.commit()
        print(f"Voided invite {args.invite_id}")  # noqa: T201


def cmd_replenish(args: argparse.Namespace) -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        user = get_user_by_email(session, args.user_email)
        replenish_quota(session, user, args.amount)
        session.commit()
        print(  # noqa: T201
            f"Replenished {args.user_email} by {args.amount} "
            f"(new balance: {user.invite_quota_remaining})"
        )


def cmd_delete(args: argparse.Namespace) -> None:
    session_factory = get_session_factory()
    with session_factory() as session:
        invite = session.get(Invite, args.invite_id)
        if invite is None:
            print(f"Invite {args.invite_id} not found")  # noqa: T201
            return

        if not args.yes:
            inviter = session.get(User, invite.inviter_id)
            inviter_label = inviter.email if inviter is not None else invite.inviter_id
            print(  # noqa: T201
                f"About to permanently delete invite {invite.id}: "
                f"invitee_email={invite.invitee_email} state={invite.state} "
                f"inviter={inviter_label}"
            )
            confirmation = input("Proceed? [y/N] ")
            if confirmation.strip().lower() != "y":
                print("Aborted")  # noqa: T201
                return

        delete_invite(session, args.invite_id)
        session.commit()
        print(f"Deleted invite {args.invite_id}")  # noqa: T201


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage account invites")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create an admin-issued invite")
    create.add_argument("--as", dest="sender_email", required=True)
    create.add_argument("--to", dest="invitee_email", required=True)
    create.set_defaults(func=cmd_create)

    void = sub.add_parser("void", help="Force-void an invite")
    void.add_argument("--id", dest="invite_id", required=True, type=uuid.UUID)
    void.set_defaults(func=cmd_void)

    replenish = sub.add_parser("replenish", help="Add to a user's invite quota")
    replenish.add_argument("--email", dest="user_email", required=True)
    replenish.add_argument("--amount", dest="amount", required=True, type=int)
    replenish.set_defaults(func=cmd_replenish)

    delete = sub.add_parser("delete", help="Permanently delete an invite")
    delete.add_argument("--id", dest="invite_id", required=True, type=uuid.UUID)
    delete.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    delete.set_defaults(func=cmd_delete)

    return parser


def main() -> int:
    """Run the manage-invites CLI."""
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
