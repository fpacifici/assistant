"""Email body templates.

Each exported `string.Template` is referenced directly by callers building
an `Email` — see `email/service.py:Email.template`.
"""

from __future__ import annotations

import string

WELCOME = string.Template("Hello $name, welcome to Assistant!")

CONFIRM_REGISTRATION = string.Template(
    "Hi $firstname,\n\n"
    "Please confirm your Assistant account by clicking the link below:\n"
    "$url\n\n"
    "This link expires in 24 hours."
)

CREDENTIAL_CHANGED = string.Template(
    "Hi $firstname,\n\n"
    "The sign-in method of your Assistant account was changed. From now on "
    "you sign in with $method.\n\n"
    "If you didn't make this change, someone else may have access to your "
    "account. Contact the Assistant administrator right away."
)

INVITE_EMAIL = string.Template(
    "Hi,\n\n"
    "$inviter_name has invited you to join Assistant. Click the link "
    "below to create your account:\n"
    "$url"
)

SHARE_NOTIFICATION_EMAIL = string.Template(
    "Hi,\n\n"
    "$granter_name shared a $subject_type with you on Assistant with "
    "$role access. View it here:\n"
    "$url"
)
