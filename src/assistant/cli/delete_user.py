"""Admin CLI for permanently deleting a user and everything they own.

Direct-DB-session script, same shape as manage_invites.py/add_evernote.py —
authorized purely by shell access. This is the highest-blast-radius
operation in the invites subsystem: deleting a user cascades through their
owned notebooks/notes and every entitlement on them, including entitlements
held by OTHER users on that content (see user_service.delete_user).
"""

from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from sqlalchemy import select

from assistant.models.database import get_session_factory
from assistant.models.schema import Entitlement, Invite, Note, Notebook
from assistant.notes.user_service import delete_user, get_user_by_email

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from assistant.models.schema import User


def _blast_radius_summary(session: Session, user: User) -> str:
    notebook_count = len(
        list(session.scalars(select(Notebook).where(Notebook.owner_id == user.uid)))
    )
    note_count = len(list(session.scalars(select(Note).where(Note.owner_id == user.uid))))
    entitlement_count = len(
        list(
            session.scalars(
                select(Entitlement).where(Entitlement.principal_id == user.uid)
            )
        )
    )
    invites_sent_count = len(
        list(session.scalars(select(Invite).where(Invite.inviter_id == user.uid)))
    )
    return (
        f"About to permanently delete user {user.email} ({user.uid}):\n"
        f"  owned notebooks: {notebook_count}\n"
        f"  owned notes: {note_count}\n"
        f"  entitlements held: {entitlement_count}\n"
        f"  invites sent: {invites_sent_count}"
    )


def main() -> int:
    """Run the delete-user CLI."""
    parser = argparse.ArgumentParser(
        description="Permanently delete a user and everything they own"
    )
    parser.add_argument("--email", dest="email", required=True)
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    args = parser.parse_args()

    session_factory = get_session_factory()
    with session_factory() as session:
        user = get_user_by_email(session, args.email)

        if not args.yes:
            print(_blast_radius_summary(session, user))  # noqa: T201
            confirmation = input("Proceed? [y/N] ")
            if confirmation.strip().lower() != "y":
                print("Aborted")  # noqa: T201
                return 0

        delete_user(session, user.uid)
        session.commit()
        print(f"Deleted user {args.email}")  # noqa: T201

    return 0


if __name__ == "__main__":
    sys.exit(main())
