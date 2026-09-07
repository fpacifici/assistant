"""Email body templates.

Each exported `string.Template` is referenced directly by callers building
an `Email` — see `email/service.py:Email.template`.
"""

from __future__ import annotations

import string

WELCOME = string.Template("Hello $name, welcome to Assistant!")
