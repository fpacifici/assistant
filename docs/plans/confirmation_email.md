# Implementation plan: Email confirmation (registration, invites, sharing)

No `docs/specs/` document exists for this feature — it was specified
directly by the user and refined in a `/grill-me` session. This plan
captures both.

## Context

Three independent gaps, closed together because they share the same
`send_email` primitive (`src/assistant/email/service.py`, built but never
called from application code) and the same domain/port link-building
convention (`invites/service.py:build_invite_url`):

1. **Registration** (`auth/service.py:register_user`) creates a `User` and
   immediately auto-logs them in (`api/routes/auth.py:register` calls
   `issue_tokens` + sets cookies right after creation, confirmed by
   `tests/api/test_auth.py:test_register_auto_logs_in`). There is no
   `is_active`/`confirmed` concept anywhere on `User`.
2. **Invites** (`invites/service.py`) already exist end-to-end (creation,
   quota, expiry, accept flow) but the invite's `id`/link is only ever
   shown in the API response (`InviteResponse.url`) and rendered as a
   plain table cell in `frontend/src/pages/InvitesPage.tsx:97` — nothing
   emails it. `GET /invites/{id}/public` deliberately omits
   `invitee_email` today ("no email verification yet" —
   `api/schemas/invites.py:32-41`).
3. **Sharing** (`notes/entitlements.py:grant_entitlement`, wired into
   `POST /notebook/{id}/share` and `POST /notebook/{id}/note/{id}/share`)
   is silent — the grantee only discovers a share by looking at the
   notebook/note.

## Decisions recap (from grilling)

**Registration**

- Accounts start `PENDING`, not active. `POST /auth/register` no longer
  auto-logs-in — it returns a "check your email" response instead
  (closing today's auto-login behavior, the opposite direction from the
  fix the invites plan made).
- Confirmation token: `secrets.token_urlsafe(32)`, hashed at rest (same
  shape as `RefreshToken`), 24h expiry, sent synchronously at registration
  time. Send failure never fails registration (logged only) — the
  response reports whether the send succeeded so the frontend can offer
  an immediate resend.
- Resend confirmation: public `POST /auth/resend-confirmation {email}`,
  rate-limited (public + unauthenticated, keyed only by email — real abuse
  surface): 1 send per 5 minutes, max 3 total sends per pending
  registration (the original send counts as attempt 1). Surfaced both on
  the post-registration "check your email" screen and on the login error
  below.
- Login checks the (new) active flag and returns a distinct, specific
  error (not generic invalid-credentials) with a resend action when the
  account isn't confirmed yet.
- Lazy cleanup, no background sweep: re-registering an email whose prior
  `PENDING` registration's confirmation has expired deletes that stale
  user (cascade) and proceeds fresh. Re-registering before expiry is left
  to hit the existing unique-email conflict unchanged.
- Confirmation-link click is a frontend route (`/confirm-email/:token`)
  calling an API endpoint and rendering success/error — not a bare
  backend redirect — mirroring `AcceptInvitePage`'s existing shape, so an
  expired/invalid token can render a proper "resend" affordance.
- Clicking an already-confirmed link a second time is treated as success
  (idempotent), not an error — no resend link shown, since there's
  nothing to resend.

**Invites**

- The invite's URL/link is removed from every API response entirely — the
  invite's own `id` (opaque identifier, needed for the existing
  void/list calls) stays, only the constructed `url` field goes.
- Invite creation — both `POST /invites` and the `manage_invites` CLI,
  routed through the same shared service functions so both send —
  emails the link synchronously at creation time. Failure doesn't fail
  creation but is reported back (`email_sent`), and a resend action is
  added for still-pending invites (no fallback link exists anymore, so a
  silent send failure would otherwise be a dead end).
- `GET /invites/{id}/public` now also returns `invitee_email`, reversing
  the earlier deliberate omission — the concern that motivated it ("no
  email verification yet") is exactly what this feature fixes. The
  registration page pre-fills (and locks) the email field from it.
- Resend-invite has no server-enforced rate limit — it's authenticated,
  sender-owned, and targets an address the inviter already chose
  deliberately, unlike the public resend-confirmation endpoint.
- Registering via an invite still triggers the standard
  registration-confirmation email — no special-casing.

**Sharing**

- Emailed on the initial grant only — not on permission changes or
  revoke. `grant_entitlement` is already idempotent (returns the existing
  row for a repeat grant), so its return value must now say whether a row
  was actually *created* — otherwise a repeat share call would re-email.
- Sent via FastAPI `BackgroundTasks` from the two share route handlers
  (not the service layer — `BackgroundTasks` only exists at the FastAPI
  layer, and sharing, unlike invites, has no CLI path to keep in sync).
  Failure is logged only, never surfaced to the caller.
- Link reuses the existing `get_domain()`/`get_port()` convention, no new
  config.

**Shared across all three**

- No new config: `Config.get_domain()`/`get_port()` (already used by
  `build_invite_url`) is reused for confirmation and share links too. The
  Mailgun-domain/app-domain conflation this implies is a pre-existing wart
  left untouched.
- No task queue exists in this repo; `BackgroundTasks` is the only async
  mechanism used, and only for sharing (registration/invite sends are
  synchronous, deliberately, since they're the critical path of a signup
  funnel).
- Every one of these three features needs an app-page link built from
  `{domain}:{port}` — the confirmation link, the invite link, and now the
  share link, each with its own path shape. Rather than repeating
  `f"https://{config.get_domain()}:{config.get_port()}/..."` at each of
  the three call sites (as an earlier draft of this plan did), a new
  `assistant.urls` module centralizes it — one function per link shape,
  all sharing the same base-URL helper. This also relocates the existing
  `invites/service.py::build_invite_url` there (renamed `invite_url`, for
  naming symmetry with its new siblings), since it's the same kind of
  link and belongs with the others once there's a shared home for them.

## New/changed files

- `src/assistant/models/schema.py` — edit. `UserStatus` enum, `User.status`,
  new `EmailConfirmation` model + `User.email_confirmation` relationship.
- `src/assistant/urls.py` — new. Centralizes every app-page link built
  from `Config.get_domain()`/`get_port()` — `invite_url` (relocated from
  `invites/service.py::build_invite_url`), `confirm_email_url`,
  `notebook_url`, `note_url`.
- `src/assistant/auth/exceptions.py` — new. `AuthError` moves here
  (was inline in `service.py`) plus five new exceptions, following the
  per-module `exceptions.py` convention already used by `invites`/`notes`/
  `email` (a small overdue consistency fix, done now because five new
  siblings are joining `AuthError`).
- `src/assistant/auth/service.py` — edit. Confirmation token lifecycle,
  lazy reap, register/login changes.
- `src/assistant/api/schemas/auth.py` — edit. `RegisterResponse`,
  `ConfirmationRequest`.
- `src/assistant/api/routes/auth.py` — edit. `register` drops auto-login;
  `login` gains a distinct not-confirmed branch; two new endpoints.
- `src/assistant/api/dependencies.py` — edit. `AuthError` import moves to
  `assistant.auth.exceptions`.
- `src/assistant/api/exceptions.py` — edit. Four new handlers.
- `src/assistant/email/templates.py` — edit. Three new templates.
- `src/assistant/invites/service.py` — edit. Email sending on
  create/admin_create, new `resend_invite`, `Config` import moves from
  `TYPE_CHECKING`-only to a real runtime import, `build_invite_url` moves
  out to `urls.py` (imported back in as `invite_url`).
- `src/assistant/api/schemas/invites.py` — edit. `InviteResponse` drops
  `url`, gains `email_sent`; `InvitePublicResponse` gains `invitee_email`.
- `src/assistant/api/routes/invites.py` — edit. New resend endpoint,
  tuple-unpacking, public-email passthrough.
- `src/assistant/cli/manage_invites.py` — edit. `cmd_create` unpacks the
  new tuple return and reports send status.
- `src/assistant/notes/entitlements.py` — edit. `grant_entitlement` returns
  `tuple[Entitlement, bool]` (created flag).
- `src/assistant/api/routes/_sharing.py` — edit. New
  `send_share_notification_email`.
- `src/assistant/api/routes/notes.py`, `.../notebooks.py` — edit. Share
  endpoints gain `BackgroundTasks`, schedule the notification iff created.
- `tests/conftest.py` — edit. New session-scoped autouse fixture setting
  `DOMAIN`/`PORT` env vars for the whole test run — every link-building
  call site (`urls.py`, transitively `auth`/`invites`/`_sharing`) needs
  `Config.get_domain()` to not raise, and this is now exercised from
  five different test files, so it goes in the root conftest once rather
  than being repeated per file.
- Tests: `tests/test_urls.py`, `tests/auth/__init__.py`,
  `tests/auth/test_service.py` (new); `tests/api/test_auth.py`,
  `tests/invites/test_service.py`, `tests/api/test_invites.py`,
  `tests/cli/test_manage_invites.py`, `tests/notes/test_entitlements.py`,
  `tests/api/test_sharing.py` (extend).
- Frontend: `frontend/src/types/index.ts`, `frontend/src/api/auth.ts`,
  `frontend/src/api/invites.ts`, `frontend/src/components/RegistrationForm.tsx`,
  `frontend/src/pages/LoginPage.tsx`, `frontend/src/pages/AcceptInvitePage.tsx`,
  `frontend/src/pages/InvitesPage.tsx`, `frontend/src/App.tsx` (edit);
  `frontend/src/pages/ConfirmEmailPage.tsx` (new). Tests:
  `RegisterPage.test.tsx`, `LoginPage.test.tsx`, `AcceptInvitePage.test.tsx`,
  `InvitesPage.test.tsx` (extend); `ConfirmEmailPage.test.tsx` (new).

## Schema (`src/assistant/models/schema.py`)

```python
class UserStatus(str, Enum):
    """Account activation state."""

    PENDING = "pending"
    ACTIVE = "active"
```

`User` gains:

```python
status: Mapped[str] = mapped_column(
    String(20), nullable=False, default=UserStatus.ACTIVE.value
)
```

The column default is `ACTIVE`, not `PENDING` — same precedent as
`invite_quota_remaining`/`Invite.quota_consumed`: a DB-level fallback for
direct inserts, not the business default. Every real creation path sets
it explicitly: `register_user` (below) sets `PENDING`;
`notes/user_service.py::create_user` — the generic `POST /user` /
admin-provisioning path, which creates no password `Credential` at all —
is **out of scope for confirmation** (see Out of scope) and so is left to
the `ACTIVE` default unchanged.

New model, plus `User.email_confirmation`:

```python
class EmailConfirmation(Base):
    """The single pending email-confirmation token for a not-yet-active User.

    One row per user — user_id IS the primary key. A resend overwrites
    this same row's token/expiry/count rather than creating a new one:
    exactly one confirmation cycle is meaningful per pending registration.
    Deleted via cascade when the User is deleted, including the lazy reap
    of an expired, still-unconfirmed registration (see
    auth.service._reap_expired_pending_registration) — no separate
    cleanup path needed.
    """

    __tablename__ = "email_confirmations"
    __table_args__ = {"schema": "assistant"}  # noqa: RUF012

    user_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("assistant.users.uid"),
        primary_key=True,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resend_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    user: Mapped[User] = relationship("User", back_populates="email_confirmation")
```

`User.email_confirmation: Mapped[EmailConfirmation | None] = relationship(
"EmailConfirmation", back_populates="user", cascade="all, delete-orphan",
uselist=False)` — added alongside the other `User` relationships. No
`created_at`: `expires_at`/`last_sent_at` are the only timestamps anything
actually reads; adding an unused audit column isn't justified here (unlike
every other table, which does use its `created_at`).

No migration step — this repo has no Alembic; `create_schema`/
`Base.metadata.create_all` picks up the new table/column on the next
`setup_database`/`reset_db` run, same as every prior schema change here.

## `src/assistant/urls.py` (new)

```python
"""App-page link builders — the links this app embeds in outgoing email.

Not to be confused with the Mailgun API URL (email/service.py builds
that separately). Every link here shares the same {domain}:{port} base
from Config, so each new email-linked page gets one function here instead
of another inline f-string at its call site.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from assistant.config import Config


def _base_url(config: Config) -> str:
    return f"https://{config.get_domain()}:{config.get_port()}"


def invite_url(invite_id: uuid.UUID, config: Config) -> str:
    """The accept-invite link — relocated from invites/service.py."""
    return f"{_base_url(config)}/invite/{invite_id}"


def confirm_email_url(token: str, config: Config) -> str:
    return f"{_base_url(config)}/confirm-email/{token}"


def notebook_url(notebook_id: uuid.UUID, config: Config) -> str:
    return f"{_base_url(config)}/notebooks/{notebook_id}"


def note_url(notebook_id: uuid.UUID, note_id: uuid.UUID, config: Config) -> str:
    return f"{_base_url(config)}/notebooks/{notebook_id}/notes/{note_id}"
```

Each function takes `config: Config` explicitly (not a fresh internal
`Config()`) — unlike `email/service.py::send_email`'s "construct its own"
convention, these are cheap pure string-builders with no I/O of their
own, so there's no reason to hide the dependency; callers that already
have a `Config()` around (or construct one to pass to `send_email`
anyway) just pass it through. `tests/test_urls.py` (new) covers all four
directly against a fixed fake `Config`, so every other test that touches
a link (`auth/service.py`, `invites/service.py`, `_sharing.py`) only
needs to assert *that* the right builder was called with the right
arguments, not re-verify the string shape itself.

## `src/assistant/auth/exceptions.py` (new)

```python
"""Auth module exceptions."""

from __future__ import annotations


class AuthError(Exception):
    """Raised when authentication fails (bad credentials, invalid/expired token)."""


class AccountNotConfirmedError(Exception):
    """Credentials were correct but the account isn't confirmed yet.

    Deliberately NOT a subclass of AuthError — the login route maps it to
    a distinct 403 with a resend-confirmation action, not the generic 401
    'Invalid credentials' AuthError maps to.
    """


class ConfirmationTokenInvalidError(Exception):
    """Confirmation token doesn't exist, or (for a still-pending user) expired.

    Deliberately not distinguished — same one-reason precedent as
    invites.exceptions.InviteNotUsableError, and for the same purpose.
    """


class ConfirmationNotFoundError(Exception):
    """No PENDING user exists for this email (covers unknown + already-active)."""


class ConfirmationCooldownError(Exception):
    """A confirmation email was already sent within the resend cooldown window."""


class ConfirmationLimitExceededError(Exception):
    """This registration has already used all MAX_CONFIRMATION_SENDS attempts."""
```

## `src/assistant/auth/service.py`

Imports gain `logging`, `select` (already imported), the new exceptions
module, `assistant.email.service`/`templates`, and
`assistant.urls.confirm_email_url`. New module constants:

```python
CONFIRMATION_TOKEN_TTL = timedelta(hours=24)
CONFIRMATION_RESEND_COOLDOWN = timedelta(minutes=5)
MAX_CONFIRMATION_SENDS = 3

logger = logging.getLogger(__name__)
```

```python
def _send_confirmation_email_best_effort(user: User, raw_token: str) -> bool:
    """Send the confirmation email synchronously; log-and-continue on failure.

    Returns whether the send succeeded. Never raises — the core
    registration/resend operation isn't hostage to Mailgun (grilling
    decision, applied identically to invites and sharing).
    """
    email = Email(
        recipient=user.email,
        subject="Confirm your Assistant account",
        template=CONFIRM_REGISTRATION,
        values={
            "firstname": user.firstname,
            "url": confirm_email_url(raw_token, Config()),
        },
    )
    try:
        send_email(email)
    except (EmailValidationError, EmailTemplateError, EmailSendError):
        logger.exception("Failed to send confirmation email to %s", user.email)
        return False
    return True


def create_email_confirmation(session: Session, user_id: uuid_module.UUID) -> str:
    """Create or overwrite the (one, per-user) pending EmailConfirmation row.

    Returns the raw token. Used both for the initial send (register_user)
    and for resend_confirmation — 'issue a fresh token and reset the
    clock' is exactly the same operation either way, so both share this.
    """
    raw = secrets.token_urlsafe(32)
    now = datetime.now(UTC)
    confirmation = session.get(EmailConfirmation, user_id)
    if confirmation is None:
        confirmation = EmailConfirmation(user_id=user_id, resend_count=0)
        session.add(confirmation)
    confirmation.token_hash = _hash_token(raw)
    confirmation.expires_at = now + CONFIRMATION_TOKEN_TTL
    confirmation.last_sent_at = now
    confirmation.resend_count += 1
    session.flush()
    return raw


def _reap_expired_pending_registration(session: Session, email: str) -> None:
    """Delete a stale, expired PENDING user for this email, if any.

    The entire 'lazy cleanup' mechanism — no background sweep. A still-live
    pending registration (not yet expired) is left alone; the subsequent
    INSERT hits the existing unique-email constraint and surfaces as the
    same 409 duplicate-email response an active user would produce.
    """
    existing = session.scalar(select(User).where(User.email == email))
    if existing is None or existing.status != UserStatus.PENDING.value:
        return
    confirmation = session.get(EmailConfirmation, existing.uid)
    now = datetime.now(UTC)
    if confirmation is not None and confirmation.expires_at.replace(tzinfo=UTC) >= now:
        return
    session.delete(existing)
    session.flush()
```

`register_user` changes: reap before creating, set `status=PENDING`,
create the confirmation row + send, return `tuple[User, bool]` instead of
`User`:

```python
def register_user(  # noqa: PLR0913
    session: Session,
    *,
    email: str,
    password: str,
    firstname: str,
    lastname: str,
    invite_id: uuid_module.UUID | None = None,
) -> tuple[User, bool]:
    """Create a user (PENDING) and a password credential; send confirmation.

    Returns (user, confirmation_email_sent) — registration never fails
    just because the send did.
    """
    config = Config().get_registration_config()
    invite = resolve_registration_gate(session, config, email, invite_id)
    _reap_expired_pending_registration(session, email)

    user = User(
        email=email,
        firstname=firstname,
        lastname=lastname,
        status=UserStatus.PENDING.value,
        invite_quota_remaining=default_quota_for_new_user(config, None),
    )
    session.add(user)
    session.flush()

    credential = Credential(
        user_id=user.uid, provider="password", credential_hash=_ph.hash(password)
    )
    session.add(credential)
    session.flush()

    on_user_created(session, user, used_invite_id=invite.id if invite else None)

    raw_token = create_email_confirmation(session, user.uid)
    email_sent = _send_confirmation_email_best_effort(user, raw_token)
    return user, email_sent
```

`authenticate_user` gains the status check, after password verification
(never leak account state before proving the password):

```python
    try:
        _ph.verify(credential.credential_hash, password)
    except VerifyMismatchError as exc:
        raise AuthError("Invalid credentials") from exc  # noqa: TRY003

    if user.status != UserStatus.ACTIVE.value:
        raise AccountNotConfirmedError

    return user
```

New confirmation-lifecycle functions:

```python
def confirm_email(session: Session, raw_token: str) -> User:
    """Activate the account raw_token was issued for.

    Idempotent: a token whose user is already ACTIVE returns that user
    without error — a second click on the same link is not a failure.
    Raises ConfirmationTokenInvalidError if the token doesn't exist, or
    (for a still-PENDING user) has expired — deliberately not
    distinguished from each other, same as InviteNotUsableError.
    """
    confirmation = session.scalar(
        select(EmailConfirmation).where(
            EmailConfirmation.token_hash == _hash_token(raw_token)
        )
    )
    if confirmation is None:
        raise ConfirmationTokenInvalidError
    user = session.get(User, confirmation.user_id)
    if user is None:
        raise ConfirmationTokenInvalidError
    if user.status == UserStatus.ACTIVE.value:
        return user
    if confirmation.expires_at.replace(tzinfo=UTC) < datetime.now(UTC):
        raise ConfirmationTokenInvalidError
    user.status = UserStatus.ACTIVE.value
    session.flush()
    return user


def resend_confirmation(session: Session, email: str) -> bool:
    """Issue a fresh confirmation token + email for a still-pending registration.

    Returns confirmation_email_sent, same best-effort contract as
    registration. Raises ConfirmationNotFoundError if no PENDING user
    exists for this email (covers both 'no such user' and 'already
    confirmed' — not distinguished, same reasoning as
    ConfirmationTokenInvalidError). Raises ConfirmationCooldownError if
    the last send was under CONFIRMATION_RESEND_COOLDOWN ago. Raises
    ConfirmationLimitExceededError once MAX_CONFIRMATION_SENDS is used —
    the only recovery then is to let the 24h window lapse and register
    again (_reap_expired_pending_registration).
    """
    user = session.scalar(select(User).where(User.email == email))
    if user is None or user.status != UserStatus.PENDING.value:
        raise ConfirmationNotFoundError
    confirmation = session.get(EmailConfirmation, user.uid)
    if confirmation is None:
        raise ConfirmationNotFoundError

    now = datetime.now(UTC)
    if now - confirmation.last_sent_at.replace(tzinfo=UTC) < CONFIRMATION_RESEND_COOLDOWN:
        raise ConfirmationCooldownError
    if confirmation.resend_count >= MAX_CONFIRMATION_SENDS:
        raise ConfirmationLimitExceededError

    raw_token = create_email_confirmation(session, user.uid)
    return _send_confirmation_email_best_effort(user, raw_token)
```

## `src/assistant/api/schemas/auth.py`

```python
class RegisterResponse(BaseModel):
    """Returned by POST /auth/register — registration no longer auto-logs-in."""

    email: str
    confirmation_email_sent: bool


class ConfirmationRequest(BaseModel):
    """Request body for POST /auth/resend-confirmation."""

    email: EmailStr
```

`RegisterRequest`/`LoginRequest`/`UserResponse` are unchanged.

## `src/assistant/api/routes/auth.py`

`register` drops the `Request`/`Response` params and all cookie logic —
registration no longer establishes a session:

```python
@router.post("/register", status_code=201, response_model=RegisterResponse)
def register(body: RegisterRequest, session: SessionDep) -> RegisterResponse:
    try:
        user, email_sent = register_user(
            session,
            email=body.email,
            password=body.password,
            firstname=body.firstname,
            lastname=body.lastname,
            invite_id=body.invite_id,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc
    return RegisterResponse(email=user.email, confirmation_email_sent=email_sent)
```

`login` gains a branch for the new exception, checked before the generic
one (order is irrelevant here since the two types are unrelated, but it
reads top-to-bottom as "more specific first"):

```python
    try:
        user = authenticate_user(session, email=body.email, password=body.password)
    except AccountNotConfirmedError as exc:
        raise HTTPException(
            status_code=403,
            detail="Account not confirmed — check your email or request a new link",
        ) from exc
    except AuthError as exc:
        raise HTTPException(status_code=401, detail="Invalid credentials") from exc
```

New endpoints, token in the path (matches `GET /invites/{invite_id}/public`'s
convention), email in the body (matches `LoginRequest`/`RegisterRequest`):

```python
@router.post("/confirm-email/{token}", status_code=204)
def confirm_email_endpoint(token: str, session: SessionDep) -> Response:
    confirm_email(session, token)
    return Response(status_code=204)


@router.post("/resend-confirmation", status_code=204)
def resend_confirmation_endpoint(
    body: ConfirmationRequest, session: SessionDep
) -> Response:
    resend_confirmation(session, body.email)
    return Response(status_code=204)
```

Both `confirm_email`/`resend_confirmation`'s exceptions propagate to the
global handlers in `api/exceptions.py` (below) — no local try/except,
matching how invites' route functions never catch their own service
exceptions either.

## `src/assistant/api/dependencies.py`

One-line change: `from assistant.auth.service import AuthError,
decode_access_token` becomes `from assistant.auth.exceptions import
AuthError` + `from assistant.auth.service import decode_access_token`.

## `src/assistant/api/exceptions.py`

Four new handlers, same shape as the existing six invites ones:

| Exception | Status |
|---|---|
| `ConfirmationTokenInvalidError` | 404 |
| `ConfirmationNotFoundError` | 404 |
| `ConfirmationCooldownError` | 429 |
| `ConfirmationLimitExceededError` | 403 |

`ConfirmationLimitExceededError` → 403 (not 429) deliberately: it isn't a
transient "try later" state like the cooldown, it's a hard stop for this
registration cycle — same status-code family as `QuotaExhaustedError`/
`InvitePermissionError`, which use 403 for the same "you've used up your
allowance" shape.

## `src/assistant/email/templates.py`

```python
CONFIRM_REGISTRATION = string.Template(
    "Hi $firstname,\n\n"
    "Please confirm your Assistant account by clicking the link below:\n"
    "$url\n\n"
    "This link expires in 24 hours."
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
```

## `src/assistant/invites/service.py`

`Config` moves from the `TYPE_CHECKING`-only import to a real runtime
import (it's now instantiated, not just used as a type hint). The
existing `build_invite_url` function is deleted from this file — it
relocates to `assistant.urls.invite_url` (see above); every caller in
this module imports it from there instead. New imports: `logging`,
`assistant.email.service.{Email, send_email}`,
`assistant.email.exceptions.{EmailSendError, EmailTemplateError,
EmailValidationError}`, `assistant.email.templates.INVITE_EMAIL`,
`assistant.urls.invite_url`.

```python
logger = logging.getLogger(__name__)


def _send_invite_email_best_effort(invite: Invite) -> bool:
    """Send the invite email synchronously; log-and-continue on failure."""
    email = Email(
        recipient=invite.invitee_email,
        subject="You've been invited to Assistant",
        template=INVITE_EMAIL,
        values={
            "inviter_name": f"{invite.inviter.firstname} {invite.inviter.lastname}",
            "url": invite_url(invite.id, Config()),
        },
    )
    try:
        send_email(email)
    except (EmailValidationError, EmailTemplateError, EmailSendError):
        logger.exception("Failed to send invite email to %s", invite.invitee_email)
        return False
    return True
```

`create_invite`/`admin_create_invite` now return `tuple[Invite, bool]`;
`_create_invite_row` is unchanged (still returns a bare `Invite`, the two
public functions wrap it):

```python
def create_invite(
    session: Session, inviter: User, invitee_email: str, config: RegistrationConfig
) -> tuple[Invite, bool]:
    if not config["invites_enabled"]:
        raise InvitesDisabledError
    if inviter.invite_quota_remaining <= 0:
        raise QuotaExhaustedError
    inviter.invite_quota_remaining -= 1
    invite = _create_invite_row(session, inviter, invitee_email, config, quota_consumed=True)
    return invite, _send_invite_email_best_effort(invite)


def admin_create_invite(
    session: Session, inviter: User, invitee_email: str, config: RegistrationConfig
) -> tuple[Invite, bool]:
    invite = _create_invite_row(session, inviter, invitee_email, config, quota_consumed=False)
    return invite, _send_invite_email_best_effort(invite)
```

New `resend_invite`, reusing `get_valid_pending_invite` for the
exists/pending/unexpired/kill-switch check (so a resend on an expired or
already-voided invite fails the same generic way redemption does):

```python
def resend_invite(
    session: Session, actor: User, invite_id: uuid.UUID, config: RegistrationConfig
) -> tuple[Invite, bool]:
    """Re-send the invite email for a still-usable invite the actor sent.

    Raises InvitePermissionError if actor isn't the sender.
    Raises InvitesDisabledError / InviteNotUsableError per
    get_valid_pending_invite — an expired or already-voided/converted
    invite has nothing to resend. No rate limit (see grilling recap).
    """
    invite = get_valid_pending_invite(session, invite_id, config)
    if invite.inviter_id != actor.uid:
        raise InvitePermissionError
    return invite, _send_invite_email_best_effort(invite)
```

## `src/assistant/api/schemas/invites.py`

```python
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
```

`InviteCreate`/`InvitesConfigResponse` are unchanged.

## `src/assistant/api/routes/invites.py`

```python
def _invite_response(
    invite: Invite, *, email_sent: bool | None = None
) -> InviteResponse:
    return InviteResponse(
        id=invite.id,
        invitee_email=invite.invitee_email,
        state=InviteState(invite.state),
        created_at=invite.created_at,
        expires_at=invite.expires_at,
        email_sent=email_sent,
    )
```

(No `config: Config` param anymore — `_invite_response` no longer builds a
URL, so it no longer needs one.)

```python
@router.get("/{invite_id}/public", response_model=InvitePublicResponse)
def get_invite_public(invite_id: uuid.UUID, session: SessionDep) -> InvitePublicResponse:
    config = Config().get_registration_config()
    try:
        invite = get_valid_pending_invite(session, invite_id, config)
    except (InviteNotUsableError, InvitesDisabledError):
        return InvitePublicResponse(valid=False)
    return InvitePublicResponse(valid=True, invitee_email=invite.invitee_email)


@router.post("", status_code=201, response_model=InviteResponse)
def create_invite_endpoint(
    body: InviteCreate, session: SessionDep, user: CurrentUser
) -> InviteResponse:
    config = Config().get_registration_config()
    invite, email_sent = create_invite(session, user, body.invitee_email, config)
    return _invite_response(invite, email_sent=email_sent)


@router.get("", response_model=list[InviteResponse])
def list_invites_endpoint(session: SessionDep, user: CurrentUser) -> list[InviteResponse]:
    invites = list_invites_for_user(session, user)
    return [_invite_response(invite) for invite in invites]


@router.post("/{invite_id}/resend", response_model=InviteResponse)
def resend_invite_endpoint(
    invite_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> InviteResponse:
    config = Config().get_registration_config()
    invite, email_sent = resend_invite(session, user, invite_id, config)
    return _invite_response(invite, email_sent=email_sent)
```

`void_invite_endpoint` is unchanged.

## `src/assistant/cli/manage_invites.py`

`cmd_create` unpacks the new tuple:

```python
def cmd_create(args: argparse.Namespace) -> None:
    config = Config().get_registration_config()
    session_factory = get_session_factory()
    with session_factory() as session:
        sender = get_user_by_email(session, args.sender_email)
        invite, email_sent = admin_create_invite(session, sender, args.invitee_email, config)
        session.commit()
        sent_note = "email sent" if email_sent else "EMAIL SEND FAILED"
        print(  # noqa: T201
            f"Created invite {invite.id} for {args.invitee_email} "
            f"(as {args.sender_email}, quota not consumed, {sent_note})"
        )
```

This means `manage_invites create` now needs the same `DOMAIN`/`MAILGUN_*`
configuration the API server needs — a natural consequence of the CLI
sharing the service layer with the API (per the Q17 decision), not a new
requirement to design around.

## `src/assistant/notes/entitlements.py`

`grant_entitlement` returns whether it actually created a row, so callers
can tell a fresh grant from the existing idempotent-return-existing-row
case:

```python
def grant_entitlement(  # noqa: PLR0913
    session: Session,
    granter: User,
    *,
    note_id: uuid.UUID | None = None,
    notebook_id: uuid.UUID | None = None,
    grantee_email: str,
    role_name: RoleName,
) -> tuple[Entitlement, bool]:
    """Grant `role_name` on the given subject to the user with `grantee_email`.

    Returns (entitlement, created) — created is False when an identical
    grant already existed (the idempotent case), which callers use to
    decide whether to send a share notification (only on an actual new
    grant, per spec).
    """
    ...
    existing = session.scalar(...)
    if existing is not None:
        return existing, False

    entitlement = Entitlement(...)
    session.add(entitlement)
    session.flush()
    return entitlement, True
```

`revoke_entitlement`/`list_entitlements` are unchanged.

## `src/assistant/api/routes/_sharing.py`

New imports: `logging`, `uuid`, `assistant.config.Config`,
`assistant.email.service.{Email, send_email}`, the three email
exceptions, `assistant.email.templates.SHARE_NOTIFICATION_EMAIL`,
`assistant.urls.{notebook_url, note_url}`.

```python
logger = logging.getLogger(__name__)


def send_share_notification_email(  # noqa: PLR0913
    *,
    granter_name: str,
    grantee_email: str,
    role: RoleName,
    subject_type: SubjectType,
    notebook_id: uuid.UUID,
    note_id: uuid.UUID | None,
) -> None:
    """Best-effort share notification. Never raises — scheduled via
    BackgroundTasks specifically so a failure here can't affect the share
    API response, and logging is therefore the only failure signal.
    """
    config = Config()
    if note_id is not None:
        url = note_url(notebook_id, note_id, config)
        subject_label = "note"
    else:
        url = notebook_url(notebook_id, config)
        subject_label = "notebook"

    email = Email(
        recipient=grantee_email,
        subject="Something was shared with you on Assistant",
        template=SHARE_NOTIFICATION_EMAIL,
        values={
            "granter_name": granter_name,
            "subject_type": subject_label,
            "role": role.value,
            "url": url,
        },
    )
    try:
        send_email(email)
    except (EmailValidationError, EmailTemplateError, EmailSendError):
        logger.exception("Failed to send share notification to %s", grantee_email)
```

## `src/assistant/api/routes/notes.py` / `.../notebooks.py`

Both share endpoints gain a `BackgroundTasks` param and schedule the
email only when `grant_entitlement` actually created a row:

```python
@router.post(
    "/{notebook_id}/note/{note_id}/share", status_code=201, response_model=EntitlementResponse
)
def share_note_endpoint(  # noqa: PLR0913
    notebook_id: uuid.UUID,
    note_id: uuid.UUID,
    body: EntitlementCreate,
    session: SessionDep,
    user: CurrentUser,
    background_tasks: BackgroundTasks,
) -> EntitlementResponse:
    _get_note_in_notebook(session, notebook_id, note_id, user)
    validate_role_for_subject_type(body.role, SubjectType.NOTE)
    entitlement, created = grant_entitlement(
        session, user, note_id=note_id, grantee_email=body.email, role_name=body.role
    )
    if created:
        background_tasks.add_task(
            send_share_notification_email,
            granter_name=f"{user.firstname} {user.lastname}",
            grantee_email=body.email,
            role=body.role,
            subject_type=SubjectType.NOTE,
            notebook_id=notebook_id,
            note_id=note_id,
        )
    return EntitlementResponse.from_entitlement(entitlement)
```

`share_notebook_endpoint` in `notebooks.py` mirrors this exactly, with
`subject_type=SubjectType.NOTEBOOK` and `note_id=None`. Both files need
`from fastapi import APIRouter, BackgroundTasks, Response` and `from
assistant.api.routes._sharing import (send_share_notification_email,
validate_role_for_subject_type)`.

## Frontend

`types/index.ts`: `Invite` drops `url`, gains `email_sent?: boolean`.

`api/auth.ts`:

```ts
export interface RegisterResult {
  email: string;
  confirmation_email_sent: boolean;
}

export function register(payload: RegisterPayload): Promise<RegisterResult> {
  return apiFetch<RegisterResult>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function confirmEmail(token: string): Promise<void> {
  return apiFetch<void>(`/auth/confirm-email/${token}`, { method: 'POST' });
}

export function resendConfirmation(email: string): Promise<void> {
  return apiFetch<void>('/auth/resend-confirmation', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}
```

`api/invites.ts`: `fetchInvitePublic` return type gains
`invitee_email: string | null`; new `resendInvite(id): Promise<Invite>`
(`POST /invites/{id}/resend`).

**`components/RegistrationForm.tsx`** — the biggest frontend change.
Gains `initialEmail?: string` / `emailLocked?: boolean` props (email
`<input>` defaults to `initialEmail` and is `readOnly` when locked).
`handleSubmit` no longer calls `login()` after `register()` (no
auto-login) and no longer navigates to `/notebooks`. Instead it renders a
post-submit pending-confirmation panel in place of the form:

```tsx
if (result) {
  return (
    <div className="auth-pending">
      <p>We sent a confirmation link to {result.email}.</p>
      {!result.confirmation_email_sent && (
        <p className="auth-error">
          The email failed to send — try resending below.
        </p>
      )}
      <ResendConfirmation email={result.email} />
      <p className="auth-footer"><Link to="/login">Back to sign in</Link></p>
    </div>
  );
}
```

`ResendConfirmation` (new small component, shared with `LoginPage` below):
a button calling `resendConfirmation(email)`, rendering the 404/429/403
responses as distinct messages ("no pending registration for this email" /
"please wait a few minutes" / "too many attempts — register again").

**`pages/LoginPage.tsx`**: `handleSubmit`'s catch gains a branch —
`err.status === 403` renders `<ResendConfirmation email={email} />` below
the form instead of the generic error text.

**`pages/AcceptInvitePage.tsx`**: passes the new fields through:

```tsx
<RegistrationForm
  inviteId={inviteId}
  initialEmail={data.invitee_email ?? undefined}
  emailLocked
/>
```

**`pages/ConfirmEmailPage.tsx`** (new), route `/confirm-email/:token`:
calls `confirmEmail(token)` in a `useMutation` fired from a mount
`useEffect`. Pending → "Confirming…"; success → "Your account is
confirmed." + `Link to="/login"`; error → "This confirmation link is no
longer valid." + `<ResendConfirmation />` (email unknown here, so this
instance takes a free-text email input rather than a fixed prop — or,
simpler, just links to `/login`, where the resend affordance already
lives via the 403 path). Mirrors `AcceptInvitePage`'s
loading/valid/invalid three-way render.

**`pages/InvitesPage.tsx`**: drops the `<td>{invite.url}</td>` column;
adds a "Resend" button next to "Void" in the pending table (a
`resendMutation` calling `resendInvite(id)`, invalidating `['invites']`
on success); shows an inline warning when a just-created or just-resent
invite's `email_sent === false`.

**`App.tsx`**: add `<Route path="/confirm-email/:token"
element={<ConfirmEmailPage />} />` to the public route group, alongside
`/login`/`/register`/`/invite/:inviteId`.

## Test plan

Following `AGENTS.md`'s convention: module-level functions, `# ---
Section ---` separators, tests before implementation per seam.

**`tests/conftest.py`** (extend) — new session-scoped autouse fixture,
same shape as `tests/api/conftest.py::_set_jwt_secret`:

```python
@pytest.fixture(scope="session", autouse=True)
def _set_test_domain() -> Iterator[None]:
    os.environ["DOMAIN"] = "test.example.com"
    os.environ["PORT"] = "8000"
    yield
    os.environ.pop("DOMAIN", None)
    os.environ.pop("PORT", None)
```

This is what makes `Config().get_domain()` not raise `ValueError` in
every test that (directly or transitively, via `register_user`/
`create_invite`/the share endpoints) now builds a link — without it,
nearly every test touched by this plan would need its own env/patch
setup just to get past link-building before it even reaches the mocked
`send_email` call.

**`tests/test_urls.py`** (new) — a `Config` built from a fixed
in-memory/temp YAML (or `test_config`-style fixture) with a known
`domain`/`port`. Cases: each of the four builders produces the expected
`https://{domain}:{port}/...` shape with the right path and interpolated
id(s); `note_url` and `notebook_url` produce different paths for the same
`notebook_id` (the note path nests under it, the notebook path doesn't).

**`tests/auth/__init__.py`, `tests/auth/test_service.py`** (new) — first
dedicated unit-test file for `auth/service.py` (previously only
API-level); justified now given the amount of pure confirmation-lifecycle
logic worth testing in isolation from FastAPI. Mock `send_email`
(`patch("assistant.auth.service.send_email")`) throughout. Cases:
`create_email_confirmation` creates a row with `resend_count=1` on first
call, overwrites `token_hash`/`expires_at`/increments `resend_count` on a
second call for the same user (not a new row — assert via `session.get`
still returns one row); `confirm_email` activates a `PENDING` user and
flips `status`; raises `ConfirmationTokenInvalidError` for an unknown
token; raises the same for an expired-and-still-`PENDING` token; returns
the user with no error for a token whose user is already `ACTIVE`
(idempotent — assert no exception, not just "doesn't crash");
`resend_confirmation` raises `ConfirmationNotFoundError` for an unknown
email and for an already-`ACTIVE` user's email; raises
`ConfirmationCooldownError` when called again inside 5 minutes of
`last_sent_at`; succeeds and increments `resend_count` when called after
the cooldown; raises `ConfirmationLimitExceededError` on the 4th attempt
(1 initial + 3 resends... i.e. once `resend_count` reaches
`MAX_CONFIRMATION_SENDS`); `_reap_expired_pending_registration` deletes a
`PENDING` user whose confirmation has expired (assert the row and its
`EmailConfirmation`/`Credential` are gone via cascade) and leaves an
unexpired `PENDING` user and any `ACTIVE` user untouched;
`register_user` sets `status=PENDING`, creates exactly one
`EmailConfirmation` row, calls `send_email` once, and returns
`email_sent=True`; when `send_email` raises `EmailSendError`,
`register_user` still returns the created user with `email_sent=False`
(registration itself doesn't fail); `authenticate_user` raises
`AccountNotConfirmedError` (not `AuthError`) for a `PENDING` user with
the right password, and still raises plain `AuthError` for a `PENDING`
user with the *wrong* password (status check happens after, not instead
of, credential verification).

**`tests/api/test_auth.py`** (extend) — `test_register_auto_logs_in` is
now wrong and gets replaced with `test_register_does_not_log_in` (asserts
no `access_token` cookie, `response.json()["confirmation_email_sent"]` is
present); registration response no longer has `uid`/`invite_quota_remaining`
(shape changed to `RegisterResponse`) — update any test asserting on
the old shape. New: full flow —
register → `client.post("/auth/login", ...)` with correct password → 403
with the not-confirmed detail; `client.post(f"/auth/confirm-email/{token}")`
(token captured by mocking `create_email_confirmation`'s
`secrets.token_urlsafe` or by reading it off the DB row directly via
`db_session`) → 204, then login → 200 + cookies set; confirming a bogus
token → 404; confirming an expired token (insert an `EmailConfirmation`
row with `expires_at` in the past directly via `db_session`) → 404;
double-confirming the same valid token → 204 both times (idempotent);
`resend-confirmation` for an unknown email → 404; for an email confirmed
less than 5 minutes ago → 429; exhausting `MAX_CONFIRMATION_SENDS` → 403
on the next attempt.

**`tests/invites/test_service.py`** (extend) — add an autouse fixture
mocking `assistant.invites.service.send_email` (domain/port are already
covered by the root `_set_test_domain` fixture above) so every existing
`create_invite`/`admin_create_invite` test keeps working unmodified for
its non-email assertions, plus new cases: `create_invite` returns `(invite, True)` when
the mocked send succeeds, `(invite, False)` when it raises
`EmailSendError` — and the invite row exists either way (creation isn't
rolled back on send failure); `resend_invite` raises
`InvitePermissionError` for a non-sender; raises `InviteNotUsableError`
for a voided/converted/expired invite (nothing to resend); succeeds and
calls `send_email` again for a valid pending invite regardless of how
many times it's called (no rate limit, per Q19 — call it 3+ times in one
test and assert no exception).

**`tests/api/test_invites.py`** (extend) — mock the send the same way.
`POST /invites` response no longer has `url`; has `email_sent: true`
(mocked success) — flip the mock to raise and assert `email_sent: false`
while the invite still appears in a subsequent `GET /invites`. New
`POST /invites/{id}/resend`: 403 for a non-sender, 404 for an
already-voided invite, 200 + `email_sent` for the sender on a pending
one. `GET /invites/{id}/public` now returns `invitee_email` matching the
invite for a valid one, and `null` for an invalid one.

**`tests/cli/test_manage_invites.py`** (extend) — mock `send_email` at
`assistant.invites.service.send_email`; `create --as --to` still creates
the invite and now also prints a send-status note (assert on stdout
containing "email sent" / "EMAIL SEND FAILED" for the two mocked
outcomes) — the underlying quota/`quota_consumed` assertions are
unchanged.

**`tests/notes/test_entitlements.py`** (extend) — `grant_entitlement`
call sites in existing tests now unpack `(entitlement, created)`; add a
case asserting `created=True` on a fresh grant and `created=False` (same
entitlement `id` returned) on an immediately-repeated identical grant.

**`tests/api/test_sharing.py`** (extend) — mock
`assistant.api.routes._sharing.send_email`. `POST .../share` (both note
and notebook variants) triggers exactly one `send_email` call on a fresh
grant (FastAPI's `TestClient` runs `BackgroundTasks` synchronously within
the request, so this is assertable directly after the `client.post`
returns, no polling needed); repeating the identical share call a second
time does **not** call `send_email` again (idempotent-grant path, no
notification); a failing mocked send doesn't affect the share response
(`response.status_code == 201`, entitlement still returned normally).

**Frontend**: `RegisterPage.test.tsx` — update the success-path
assertion: no `login` call, no navigation to `/notebooks`; instead the
pending-confirmation panel renders with the registered email.
`LoginPage.test.tsx` — a mocked 403 `ApiError` renders the resend
affordance instead of the generic error. `AcceptInvitePage.test.tsx` —
the email input is pre-filled and `readOnly` when
`fetchInvitePublic` resolves `invitee_email`. `InvitesPage.test.tsx` — no
URL column rendered; clicking "Resend" calls `resendInvite`.
`ConfirmEmailPage.test.tsx` (new) — mocked success renders the confirmed
message + login link; mocked 404 renders the invalid message.

## Build order

1. Schema (`UserStatus`, `User.status`, `EmailConfirmation`). Sanity-check
   with `pytest tests/models` — additive, expect no failures.
2. `tests/conftest.py` (`_set_test_domain` autouse fixture) +
   `tests/test_urls.py` → `urls.py` (new). Do this before anything that
   consumes it (steps 4, 6, 7) — every later step's tests rely on the
   root fixture already being in place.
3. `auth/exceptions.py` (new) + `auth/dependencies.py`/`api/exceptions.py`
   import-path updates for the moved `AuthError` — do this in isolation
   first and run `make check` to confirm the refactor alone is clean
   before layering new behavior on top.
4. `email/templates.py` (three new templates) — trivial, no tests beyond
   what the send-path tests exercise indirectly.
5. TDD `tests/auth/test_service.py` → `auth/service.py` (confirmation
   lifecycle, reap, register/authenticate changes). Depends on 1-4.
6. `api/schemas/auth.py` + `api/routes/auth.py` (register/login changes,
   two new endpoints) + the four new `api/exceptions.py` handlers. TDD
   against extended `tests/api/test_auth.py`. Depends on 5.
7. `invites/service.py` (email sending, `resend_invite`, `Config` import
   change) + `api/schemas/invites.py` + `api/routes/invites.py` +
   `cli/manage_invites.py`. TDD against extended
   `tests/invites/test_service.py`, `tests/api/test_invites.py`,
   `tests/cli/test_manage_invites.py`. Independent of 5-6, depends only
   on 2 and 4.
8. `notes/entitlements.py` (tuple return) + `api/routes/_sharing.py`
   (notification function) + `notes.py`/`notebooks.py` route changes. TDD
   against extended `tests/notes/test_entitlements.py`,
   `tests/api/test_sharing.py`. Independent of 5-7, depends only on 2
   and 4.
9. Frontend: types, `api/auth.ts`, `api/invites.ts`, `RegistrationForm`
   (+ new `ResendConfirmation`), `LoginPage`, `AcceptInvitePage`,
   `ConfirmEmailPage` (new), `InvitesPage`, `App.tsx` route. Depends on
   6-8 (needs the real API shapes). TDD against the extended/new
   `*.test.tsx` files.
10. `make check` (backend) + `make frontend-check` + `make frontend-test`
    across everything touched.

## Verification

- `make check` passes (mypy strict, ruff, full pytest suite).
- `make frontend-check && make frontend-test` pass.
- Manual smoke test: `make services-up`, `python -m assistant.cli.setup_database`,
  point `DOMAIN`/`MAILGUN_*` env vars at a real or sandbox Mailgun domain;
  register a user at `/register`, confirm the "check your email" panel
  appears and an email actually arrives; try logging in before
  confirming → 403 + resend link shown; click the confirmation link from
  the real email → lands on `/confirm-email/:token`, shows success, log
  in now works; from another account, send an invite at `/invites` and
  confirm the invitee receives an email (not just a URL in the table);
  click that link → lands on `/invite/:id` with the email field
  pre-filled and locked, register → confirmation email arrives as above;
  request `resend-confirmation` for a still-pending registration twice
  within 5 minutes → second returns 429 in the UI; share a note with a
  third registered user → that user receives a "shared with you" email
  with a working link; share the same note with them again → no second
  email.

## Out of scope

- `notes/user_service.py::create_user` (generic `POST /user` /
  admin-provisioning path) — not gated by confirmation. It creates no
  password `Credential`, so there is no login path for it to block; the
  spec's "when a user registers" language is about self-service
  registration (`/auth/register`), not this path.
- A countdown/`retry_after` value on the 429 cooldown response — the
  frontend shows a static "wait a few minutes" message, not a live timer.
- Any CLI `resend` command for invites (only exposed via the API/frontend
  per the grilling session — Q17 only covered invite *creation* parity).
- Notifying on permission changes or revoke (sharing emails fire on
  initial grant only, per spec and Q7).
- Rate-limiting invite creation/resend beyond what already exists (quota
  for creation, none for resend — Q19).
- A background sweep for expired, unconfirmed registrations or expired
  invites — both stay lazy (checked only when read/registered-against
  again), consistent with how invite expiry already works.
- Any change to `email/service.py` itself, or to `Config` — this plan
  only adds callers and templates.

## Further notes

- `grant_entitlement`'s and `create_invite`/`admin_create_invite`'s
  return-type changes (`X` → `tuple[X, bool]`) are breaking changes to
  those functions' public signatures. Every call site in this plan is
  accounted for (routes, CLI, tests), but this is worth flagging clearly
  in the PR description since it's not purely additive.
- `invites/service.py` gains a new `auth`-shaped dependency on
  `assistant.email` (previously it depended only on its own exceptions
  and `models.schema`), and `_sharing.py` (previously dependency-free
  besides `fastapi`/`models.schema`) gains the same. Both are new module
  edges, directionally fine (nothing in `email` imports back), but worth
  noting since `email` was built as a leaf module nothing used yet.
- `AuthError`'s relocation from `auth/service.py` to `auth/exceptions.py`
  touches two import sites (`api/dependencies.py`, `api/routes/auth.py`)
  that have nothing else to do with this feature — called out here so
  it isn't mistaken for scope creep during review.
- Similarly, `build_invite_url`'s relocation/rename to
  `assistant.urls.invite_url` touches `invites/service.py`'s import list
  even though its behavior is unchanged — the only pre-existing function
  this plan moves rather than adds. Both relocations exist for the same
  reason: a module gained enough siblings (five exceptions; three more
  link builders) to justify a dedicated home it didn't need before.
