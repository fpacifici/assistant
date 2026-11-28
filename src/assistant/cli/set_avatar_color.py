"""Admin CLI to set the colour a user's avatar and cursor show on shared notes.

Direct-DB-session script, same shape as delete_user.py: authorized purely by
shell access.

    python -m assistant.cli.set_avatar_color --list
    python -m assistant.cli.set_avatar_color --email leda@example.com --color pink
    python -m assistant.cli.set_avatar_color --email leda@example.com --clear
"""

from __future__ import annotations

import argparse
import sys

from assistant.models.database import get_session_factory
from assistant.notes.avatar_colors import AVATAR_COLORS
from assistant.notes.exceptions import UserNotFoundError
from assistant.notes.user_service import get_user_by_email, set_avatar_color


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Set a user's avatar colour on shared notes",
    )
    parser.add_argument("--list", action="store_true", help="List the colours and exit")
    parser.add_argument("--email", help="The user to change")
    choice = parser.add_mutually_exclusive_group()
    choice.add_argument("--color", choices=list(AVATAR_COLORS), help="Colour name")
    choice.add_argument(
        "--clear",
        action="store_true",
        help="Forget the preference: pick the colour from the user id",
    )
    args = parser.parse_args()
    if not args.list:
        if args.email is None:
            parser.error("--email is required")
        if args.color is None and not args.clear:
            parser.error("pass --color or --clear")
    return args


def main() -> int:
    """Run the set-avatar-color CLI."""
    args = _parse_args()
    if args.list:
        for name, css in AVATAR_COLORS.items():
            print(f"{name:<8} {css}")  # noqa: T201
        return 0

    color: str | None = None if args.clear else args.color
    session_factory = get_session_factory()
    with session_factory() as session:
        try:
            user = get_user_by_email(session, args.email)
        except UserNotFoundError:
            print(f"No user with email {args.email}", file=sys.stderr)  # noqa: T201
            return 1
        set_avatar_color(session, user.uid, color)
        session.commit()
    shown = color or "picked from the user id"
    print(f"Avatar colour of {args.email}: {shown}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
