# Implementation plan: Add email service

Implements `docs/specs/0004_add_email_service.md`, per the decisions reached
in the `/grill-me` session on this spec.

## Context

There is currently no way for the backend to send email. This plan adds a
self-contained `email` package that lets other product features send a
templated, text-only message through Mailgun's HTTP API, following the same
shape as the existing `attachments/` module (a `service.py` of free
functions plus a dedicated `exceptions.py`) and `config.py`'s existing
TypedDict + `Config.get_*` pattern (mirroring `get_database_config()`).

Nothing in the codebase calls this service yet — this plan only builds the
abstraction itself, not any caller (e.g. no notification-on-signup feature).
`requests` is not currently a dependency and must be added.

## Decisions recap (from grilling)

- Package, not a single file: `src/assistant/email/` with `service.py`,
  `exceptions.py`, `templates.py` — matching `attachments/`'s convention
  rather than the spec's literal "add an `email.py`" wording.
- `MailgunConfig` TypedDict grows to four fields (not the two the spec
  describes): `api_url`, `api_key`, `sender`, `timeout`. The literal "two
  entries" line in the spec is superseded by this session.
- `domain` is **not** part of `MailgunConfig` — it's a root-level
  `AssistantConfig` key (sibling to `document_storage_path`, etc.), read via
  a new `Config.get_domain()`, since it identifies the assistant's own
  domain rather than being Mailgun-specific config.
- `api_url` is the Mailgun API root (e.g. `https://api.mailgun.net/v3`), not
  a pre-built messages endpoint — `service.py` joins it with the root-level
  domain into `f"{api_url}/{domain}/messages"`.
- `sender` lives in config only. There is no `sender` field on `Email` and
  no per-send override — every email goes out from the one configured
  address, "for now."
- `timeout` is the only field in `MailgunConfig` that isn't fail-fast:
  `api_url`/`api_key`/`sender` (in `MailgunConfig`) and the root-level
  `domain` (via `get_domain()`) are required (raise `ValueError` if absent,
  mirroring `get_database_config()`); `timeout` defaults to `10` seconds via
  `Config.get(..., default=10)` if unset.
- `send_email` constructs its own `Config()` internally (a fresh instance
  per call, rereading YAML + env each time) rather than taking a `config`
  parameter from the caller. This is a deliberate deviation from the
  `attachments/service.py` dependency-injection convention, accepted because
  a broader refactor of config plumbing is expected later.
- `Email` fields: `recipient: str`, `subject: str` (plain string, never
  templated), `template: string.Template` (a direct object reference
  exported from `templates.py`), `values: dict[str, str]`.
- `templates.py` exports raw `string.Template` instances at module level —
  no wrapper class. "The template is just the body"; subject is a separate,
  non-templated field the caller sets directly on `Email`.
- Template substitution uses `.substitute()`, not `.safe_substitute()` —
  raise loudly (`KeyError` surfaces, or is wrapped — see below) on any
  missing/extra placeholder rather than sending a partially-filled email.
- `recipient` is validated as a well-formed address using `email-validator`
  (already a dependency) before any network call — recipients are plain
  strings and may not correspond to any registered `User`, so there's no DB
  check to fall back on.
- Sending: `requests.post` to the domain-scoped endpoint, text body only (no
  HTML), using `timeout` from config.
- Exactly one retry, only for transient failures (network/timeout exceptions
  and 5xx responses) — never for 4xx, since those are deterministic
  misconfiguration that a retry can't fix. Immediate retry, no backoff.
- All failures (validation, template, and send) raise typed exceptions from
  `email/exceptions.py`, matching `attachments/exceptions.py`'s pattern.
  `send_email` returns `None` on success — no Mailgun message ID is
  surfaced, since nothing needs delivery tracking yet.

## New/changed files

- `pyproject.toml` — edit. Add `requests` to `dependencies`.
- `src/assistant/config.py` — edit. `MailgunConfig` TypedDict; root-level
  `domain` field on `AssistantConfig`; `Config.get_mailgun_config()` and
  `Config.get_domain()`.
- `src/assistant/email/__init__.py` — new.
- `src/assistant/email/exceptions.py` — new. `EmailValidationError`,
  `EmailTemplateError`, `EmailSendError`.
- `src/assistant/email/templates.py` — new. Raw `string.Template` instances.
- `src/assistant/email/service.py` — new. `Email` dataclass, `send_email`.
- `tests/email/__init__.py`, `tests/email/test_service.py` — new.

## `src/assistant/config.py`

`domain` is a root-level `AssistantConfig` key — it identifies the
assistant's own domain, not something Mailgun-specific — so it sits
alongside `document_storage_path`/`file_storage_path`, not inside
`MailgunConfig`:

```python
class AssistantConfig(TypedDict, total=False):
    """Top-level configuration structure loaded from YAML."""

    database: DatabaseConfig
    document_storage_path: str
    file_storage_path: str
    external_sources: ExternalSourcesConfig
    domain: str
    mailgun: MailgunConfig
```

```python
class MailgunConfig(TypedDict):
    """Mailgun API configuration."""

    api_url: str
    api_key: str
    sender: str
    timeout: int
```

```python
def get_domain(self) -> str:
    """Get the assistant's configured domain.

    Env var override: `domain` -> `DOMAIN`.

    Returns:
        The configured domain.

    Raises:
        ValueError: If `domain` is missing from both YAML and env.
    """
    domain = self._get_typed_value(key="domain", expected_type=str)
    if not domain:
        msg = "Domain configuration not found (set `domain` in config or DOMAIN env var)"
        raise ValueError(msg)
    return domain
```

```python
def get_mailgun_config(self) -> MailgunConfig:
    """Get the effective Mailgun configuration with env-var overrides applied.

    Env var overrides follow the module convention:
        - `mailgun.api_url` -> `MAILGUN_API_URL`
        - `mailgun.api_key` -> `MAILGUN_API_KEY`
        - `mailgun.sender`  -> `MAILGUN_SENDER`
        - `mailgun.timeout` -> `MAILGUN_TIMEOUT`

    Note: the sending domain is not part of this config — see `get_domain()`.

    Returns:
        A `MailgunConfig` mapping.

    Raises:
        ValueError: If `api_url`, `api_key`, or `sender` is missing from
            both YAML and env. `timeout` defaults to 10 if unset.
    """
    api_url = self._get_typed_value(key="mailgun.api_url", expected_type=str)
    api_key = self._get_typed_value(key="mailgun.api_key", expected_type=str)
    sender = self._get_typed_value(key="mailgun.sender", expected_type=str)

    missing_keys: list[str] = []
    if not api_url:
        missing_keys.append("api_url")
    if not api_key:
        missing_keys.append("api_key")
    if not sender:
        missing_keys.append("sender")
    if missing_keys:
        msg = f"Mailgun configuration missing required keys: {', '.join(missing_keys)}"
        raise ValueError(msg)

    timeout = self.get("mailgun.timeout", 10)

    return {
        "api_url": api_url,
        "api_key": api_key,
        "sender": sender,
        "timeout": timeout,
    }
```

This mirrors `get_database_config()`'s shape exactly: typed per-field reads
via `_get_typed_value` (so env overrides are type-coerced the same way),
then a single missing-keys check that reports every absent field at once
rather than failing on the first one. `get_domain()` follows the same
fail-fast style as a one-field case.

`config.yaml` gains a documented (but not committed with real secrets)
example section, matching the existing `database:`/`external_sources:`
comment style:

```yaml
# The assistant's own domain (also used as the Mailgun sending domain)
domain: mg.example.com

# Mailgun configuration (api_key is always supplied via MAILGUN_API_KEY env var)
mailgun:
  api_url: https://api.mailgun.net/v3
  sender: noreply@example.com
  # timeout: 10  # optional, defaults to 10 seconds
```

## `src/assistant/email/exceptions.py`

```python
"""Email-service-specific exceptions."""

from __future__ import annotations


class EmailValidationError(Exception):
    """Raised when a recipient address fails format validation."""

    def __init__(self, address: str) -> None:
        super().__init__(f"Invalid email address: {address}")
        self.address = address


class EmailTemplateError(Exception):
    """Raised when template substitution is missing a required value."""

    def __init__(self, missing_key: str) -> None:
        super().__init__(f"Missing template value: {missing_key}")
        self.missing_key = missing_key


class EmailSendError(Exception):
    """Raised when Mailgun rejects the send or the request fails outright."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
```

`EmailTemplateError` wraps the `KeyError` raised by `.substitute()` so
callers of `send_email` only ever need to catch this package's own
exception types, never a bare stdlib `KeyError`/`ValueError`, matching how
`attachments/service.py` never lets a raw `sqlalchemy`/`OSError` escape.

## `src/assistant/email/templates.py`

```python
"""Email body templates.

Each exported `string.Template` is referenced directly by callers building
an `Email` — see `email/service.py:Email.template`.
"""

from __future__ import annotations

import string

WELCOME = string.Template("Hello $name, welcome to Assistant!")
```

Only a placeholder template is added now; real templates get added by the
features that need them, in the same module.

## `src/assistant/email/service.py`

```python
"""Email service — sends templated, text-only email via Mailgun."""

from __future__ import annotations

import string
from dataclasses import dataclass

import requests
from email_validator import EmailNotValidError, validate_email

from assistant.config import Config
from assistant.email.exceptions import EmailSendError, EmailTemplateError, EmailValidationError

_TRANSIENT_STATUS_THRESHOLD = 500


@dataclass(frozen=True)
class Email:
    """An email to send: who it's for, its subject, and its templated body."""

    recipient: str
    subject: str
    template: string.Template
    values: dict[str, str]


def _validate_recipient(recipient: str) -> None:
    try:
        validate_email(recipient, check_deliverability=False)
    except EmailNotValidError as exc:
        raise EmailValidationError(recipient) from exc


def _render_body(template: string.Template, values: dict[str, str]) -> str:
    try:
        return template.substitute(values)
    except KeyError as exc:
        raise EmailTemplateError(str(exc)) from exc


def _post(url: str, *, api_key: str, data: dict[str, str], timeout: int) -> requests.Response:
    return requests.post(url, auth=("api", api_key), data=data, timeout=timeout)


def send_email(email: Email) -> None:
    """Send an email through Mailgun.

    Raises:
        EmailValidationError: `email.recipient` is not a well-formed address.
        EmailTemplateError: `email.values` is missing a key the template needs.
        EmailSendError: Mailgun rejected the send, or the request failed
            after one retry on a transient error.
    """
    _validate_recipient(email.recipient)
    body = _render_body(email.template, email.values)

    app_config = Config()
    config = app_config.get_mailgun_config()
    domain = app_config.get_domain()
    url = f"{config['api_url']}/{domain}/messages"
    data = {
        "from": config["sender"],
        "to": email.recipient,
        "subject": email.subject,
        "text": body,
    }

    attempts = 0
    while True:
        attempts += 1
        try:
            response = _post(url, api_key=config["api_key"], data=data, timeout=config["timeout"])
        except requests.RequestException as exc:
            if attempts > 1:
                raise EmailSendError(f"Mailgun request failed: {exc}") from exc
            continue

        if response.ok:
            return

        if response.status_code < _TRANSIENT_STATUS_THRESHOLD or attempts > 1:
            raise EmailSendError(
                f"Mailgun send failed ({response.status_code}): {response.text}",
                status_code=response.status_code,
            )
        # else: transient 5xx on first attempt — loop and retry once.
```

Notes on the retry shape: the `while True` loop makes exactly one retry
possible (`attempts` reaches 2 before either returning or raising) and only
does so for a `requests.RequestException` (network/timeout) or a `>= 500`
response — a 4xx short-circuits immediately via the `attempts > 1` OR
condition being irrelevant (status < threshold is false, so it falls to
`attempts > 1`... actually a first-attempt 4xx must raise immediately, not
retry — this needs `response.status_code < 500` to raise unconditionally
regardless of `attempts`). **Implementation note to resolve during coding**:
the condition on the last `if` must be
`response.status_code < _TRANSIENT_STATUS_THRESHOLD or attempts > 1` so that
a 4xx raises on attempt 1 (left side true) and a persistent 5xx raises on
attempt 2 (right side true) — write this as a unit test first
(`test_client_error_does_not_retry`, `test_server_error_retries_once_then_raises`)
before trusting the boolean shape, since it's the easiest part of this
service to get subtly wrong.

## Test plan

Follow this repo's TDD convention: tests before implementation, per seam.

**`tests/email/test_service.py`** — new. Mock `requests.post` (via
`unittest.mock.patch("assistant.email.service.requests.post")` or
`monkeypatch`); no real Mailgun credentials or network access needed. A
fixture monkeypatches both `assistant.config.Config.get_mailgun_config` (a
fixed `MailgunConfig` dict) and `assistant.config.Config.get_domain` (a
fixed domain string), so tests never depend on `config.yaml`/env state.

Cases:
- `send_email` posts to `f"{api_url}/{domain}/messages"` with `from`/`to`/
  `subject`/`text` set from the `Email` and config.
- Success (`response.ok`) returns `None` and calls `requests.post` exactly
  once.
- Invalid recipient (e.g. `"not-an-email"`) raises `EmailValidationError`
  *before* `requests.post` is called at all (assert the mock has zero
  calls).
- A template with an unfilled `$placeholder` and no matching key in
  `values` raises `EmailTemplateError` before `requests.post` is called.
- A template with extra/unused keys in `values` still succeeds (`.substitute`
  only raises on a placeholder with no value, not the reverse).
- A single transient failure (mock raises `requests.Timeout` on the first
  call, returns a 200 on the second) succeeds and `requests.post` is called
  exactly twice.
- Two consecutive transient failures raise `EmailSendError` after exactly
  two calls (not three — confirms the loop doesn't retry more than once).
- A 4xx response (e.g. 401 bad API key) raises `EmailSendError` immediately,
  with `requests.post` called exactly once (no retry on a client error).
- A 5xx response on the first call, 5xx again on the second, raises
  `EmailSendError` after exactly two calls.
- The configured `timeout` value is passed through to `requests.post`.

**`tests/test_config.py`** (existing file — confirm exact name) — extend
with:
- `get_mailgun_config()` cases mirroring the existing `get_database_config()`
  tests: all fields present in YAML; each individual required field missing
  raises `ValueError` naming it; `MAILGUN_*` env vars override YAML;
  `timeout` defaults to `10` when absent from both YAML and env.
- `get_domain()` cases: present in YAML returns it; missing from both YAML
  and env raises `ValueError`; `DOMAIN` env var overrides YAML.

## Build order

1. `pyproject.toml`: add `requests`. `uv sync`.
2. `config.py`: root-level `domain` field + `MailgunConfig` +
   `get_mailgun_config()` + `get_domain()`. TDD against extended
   `tests/test_config.py`.
3. `email/exceptions.py`, `email/templates.py` — small, no tests needed
   beyond what `test_service.py` exercises indirectly.
4. TDD: `tests/email/test_service.py` → `email/service.py` (`Email`,
   `send_email`), paying particular attention to the retry-boundary cases
   above before writing the retry loop's conditional.
5. `make check` (mypy strict, ruff, full pytest suite).

## Verification

- `make check` passes.
- No manual/live Mailgun smoke test in this plan — nothing calls
  `send_email` yet, and the spec doesn't ask for a CLI/route to trigger a
  real send. A future feature that adopts this service is responsible for
  its own manual verification against a real Mailgun sandbox domain.

## Out of scope

- Any caller of `send_email` (notifications, digests, invites, etc.) —
  this plan only builds the abstraction.
- HTML email bodies / any MIME type beyond plain text (per spec).
- Per-send sender override, multiple recipients, cc/bcc, attachments, or
  reply-to headers — not in the spec, and explicitly ruled out for
  `sender` in the grilling session.
- Retry backoff/delay, or more than one retry.
- A dry-run/disabled mode for dev or test environments — tests mock
  `requests.post` directly instead.
- Passing `MailgunConfig` into `send_email` as an explicit parameter
  (dependency injection) — deliberately deferred to a future refactor per
  the grilling session.
- Delivery tracking / returning the Mailgun message ID.
