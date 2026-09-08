# Implementation plan: Support invites

Implements `docs/specs/0005-invites.md`, per the decisions reached in the
`/grill-me` session on that spec.

## Context

Today there are exactly two ways to create a `User`: `POST /auth/register`
(`src/assistant/auth/service.py:87-107`, `register_user`) and the generic
`POST /user` (`src/assistant/notes/user_service.py:19-25`, `create_user`,
also reachable via the `create-user` CLI subcommand of
`src/assistant/cli/api_client.py`). Neither is gateable, neither knows about
quotas, and — a pre-existing gap this plan also closes as a side effect —
`register_user` does not auto-login: only `/auth/login` calls `issue_tokens`
and sets cookies today.

This plan adds a new `assistant.invites` module (peer to `assistant.auth`,
not nested under `notes` — invites are about account creation, not
notes/notebooks), a `registration_enabled`/`invites_enabled` config gate
enforced in the service layer (not just hidden in the UI), a per-user
`invite_quota_remaining` counter, and a `manage-invites` CLI authorized
purely by shell access — mirroring the existing `setup_database`/`reset_db`
precedent, since there is no in-app admin role anywhere in this system
(confirmed: RBAC's six roles, `docs/specs/0003_role_based_access_control.md`,
are all subject-scoped).

## Decisions recap (from grilling)

- Two independent config booleans, not a mode enum; both enforced
  server-side in the service layer, not just hidden in the UI.
- `invites_enabled=false` is a full kill switch (blocks create **and**
  redeem of pending invites); `registration_enabled=false` blocks
  `/auth/register` unless a valid `invite_id` is supplied.
- Re-inviting an already-pending email always creates a **new** invite
  (never idempotent) — the recipient may have lost the original link.
- Quota: decremented on invite creation, refunded on void (manual, admin,
  or cascade), never refunded on expiry, never consumed by admin-issued
  invites (and therefore never refunded when those are voided either —
  tracked via a `quota_consumed` flag on `Invite`, since "did this
  particular invite cost anything" can't be derived from state alone once
  admin-bypass invites exist).
- Expiry (1 day) is checked lazily at read/redemption time — no background
  sweep, no stored `expired` state.
- "Regenerate URL" is a pure server-side re-derivation
  (`https://{domain}:{port}/invite/{id}`, built from the existing top-level
  `domain` config value and a new top-level `port` value, recomputed fresh
  on every `GET`) — no endpoint, no DB write, nothing to build beyond
  returning the field on every read.
- Any user-creation path (self-register, invite-accept, CLI `create-user`)
  voids+refunds every other `pending` invite for that email — one shared
  hook (`on_user_created`), not duplicated per call site.
- Accept-invite lives at a distinct frontend route (`/invite/:id`), not a
  query param on `RegisterPage`; email is pre-filled and read-only, but the
  backend still validates the submitted email against the invite.
- All four terminal/invalid invite states render one generic "no longer
  valid" message — never distinguished, to avoid leaking account existence.
- Admin CLI has no in-app authorization concept to check — it's a
  direct-DB-session script like `setup_database.py`/`add_evernote.py`, not
  an HTTP client like `api_client.py`.

## New/changed files

- `src/assistant/config.py` — edit. `RegistrationConfig` TypedDict +
  `AssistantConfig.registration` + `Config.get_registration_config()`; new
  top-level `port: int` field + `Config.get_port()`, alongside the
  already-existing top-level `domain`/`Config.get_domain()` from the email
  service.
- `src/assistant/models/schema.py` — edit. `InviteState` enum, `Invite`
  model, `User.invite_quota_remaining` + `User.invites_sent` relationship.
- `src/assistant/invites/__init__.py`, `.../exceptions.py`, `.../service.py`
  — new module.
- `src/assistant/notes/user_service.py` — edit. `create_user` gains
  `invite_quota: int | None = None`, calls `invites.service.on_user_created`;
  new `delete_user` (permanent, cascade-delete).
- `src/assistant/auth/service.py` — edit. `register_user` gains
  `invite_id: uuid.UUID | None = None`, enforces the config gate, converts
  the used invite, calls `on_user_created`.
- `src/assistant/api/routes/auth.py` — edit. `register` route: pass through
  `invite_id`, catch the new invite/registration exceptions, auto-login
  (issue tokens + set cookies) on success — closing the pre-existing gap.
- `src/assistant/api/schemas/auth.py` — edit. `RegisterRequest.invite_id:
  uuid.UUID | None`.
- `src/assistant/api/schemas/users.py` — edit. `UserCreate.invite_quota:
  int | None`; `UserResponse.invite_quota_remaining: int`.
- `src/assistant/api/schemas/invites.py` — new. Request/response models.
- `src/assistant/api/routes/invites.py` — new. CRUD + the public
  validity-check endpoint + the config-flags endpoint.
- `src/assistant/api/exceptions.py` — edit. Register the five new invite
  exception handlers.
- `src/assistant/api/app.py` — edit. Mount `invites_router`.
- `src/assistant/cli/manage_invites.py` — new. `create`/`void`/`replenish`/
  `delete` (permanent erasure, distinct from `void`).
- `src/assistant/cli/delete_user.py` — new. Permanent, confirmation-gated
  user deletion.
- `src/assistant/cli/api_client.py` — edit. `create-user` gains
  `--invite-quota`.
- Frontend: `frontend/src/types/index.ts`, `frontend/src/api/invites.ts`
  (new), `frontend/src/api/auth.ts` (edit), `frontend/src/pages/InvitesPage.tsx`
  (new), `frontend/src/pages/AcceptInvitePage.tsx` (new),
  `frontend/src/components/RegistrationForm.tsx` (new, extracted from
  `RegisterPage`), `frontend/src/pages/RegisterPage.tsx` (edit, gated on the
  config flag), `frontend/src/App.tsx` (new routes), `frontend/src/components/Layout.tsx`
  (nav link + quota badge).
- Tests: `tests/invites/test_service.py` (new), `tests/api/test_invites.py`
  (new), `tests/api/test_auth.py` (extend), `tests/cli/test_manage_invites.py`
  (new), `tests/cli/test_delete_user.py` (new), `tests/notes/test_user_service.py`
  (extend if present, else add cases to wherever `create_user` is currently
  tested), `tests/test_config.py`
  (extend); frontend `InvitesPage.test.tsx`, `AcceptInvitePage.test.tsx`.

## Config (`src/assistant/config.py`)

No stored URL — the invite link is composed at read time from the
already-existing top-level `domain` (added by the email-service merge,
`config.py:49-58` post-merge) plus a new top-level `port`, never persisted
alongside the invite itself:

```python
class RegistrationConfig(TypedDict, total=False):
    """Registration/invite subsystem configuration."""

    registration_enabled: bool
    invites_enabled: bool
    default_quota: int
    expiry_days: int


class AssistantConfig(TypedDict, total=False):
    database: DatabaseConfig
    document_storage_path: str
    file_storage_path: str
    external_sources: ExternalSourcesConfig
    domain: str  # already present (email service)
    port: int
    mailgun: MailgunConfig  # already present (email service)
    registration: RegistrationConfig
```

```python
def get_port(self) -> int:
    """Get the assistant's configured port, defaulting to 8000.

    Env var override: `port` -> `PORT`.
    """
    return int(self.get("port", 8000))


def get_registration_config(self) -> RegistrationConfig:
    """Effective registration/invites config, env-overridable per key (REGISTRATION_*)."""
    return {
        "registration_enabled": bool(
            self.get("registration.registration_enabled", True)
        ),
        "invites_enabled": bool(self.get("registration.invites_enabled", True)),
        "default_quota": int(self.get("registration.default_quota", 5)),
        "expiry_days": int(self.get("registration.expiry_days", 1)),
    }
```

Follows the existing `get_database_config`/`get_external_source_config`/
`get_domain` pattern exactly — a typed getter wrapping `.get()` calls, each
individually env-overridable via `REGISTRATION_REGISTRATION_ENABLED` /
`REGISTRATION_INVITES_ENABLED` / `REGISTRATION_DEFAULT_QUOTA` /
`REGISTRATION_EXPIRY_DAYS` (`_env_var_name`'s dotted-key convention), plus
`PORT` for the new top-level key. Defaults (`True`/`True`/`5`/`1`/`8000`)
keep today's fully-open dev behavior unchanged for anyone who doesn't add a
`registration:` section to `config.yaml`. Unlike `port`, `domain` has no
default — `get_domain()` already raises `ValueError` if it's unset in both
YAML and env, a failure mode invite-URL composition now shares with the
email service, which depends on the same call.

## Schema (`src/assistant/models/schema.py`)

```python
class InviteState(str, Enum):
    """Lifecycle state of an account Invite. Only PENDING transitions."""

    PENDING = "pending"
    VOID = "void"
    CONVERTED = "converted"


class Invite(Base):
    """A pending account invite for an email with no matching User yet."""

    __tablename__ = "invites"
    __table_args__ = {"schema": "assistant"}

    id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid_module.uuid4,
    )
    invitee_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    inviter_id: Mapped[uuid_module.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("assistant.users.uid"), nullable=False,
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False, default=InviteState.PENDING.value)
    quota_consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC),
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    inviter: Mapped[User] = relationship("User", back_populates="invites_sent")
```

`state`/`quota_consumed` are unconstrained at the DB level, validated only in
the service layer — same precedent as `Node.node_type`/`Node.block_type` and
(most directly) `Entitlement.role_name`: a small fixed enum stored as a plain
column, no DB `CHECK`. No `invitee_email` uniqueness — the spec explicitly
allows multiple pending invites (from the same or different senders) to the
same address.

`quota_consumed` exists specifically because "did voiding this invite cost
its sender anything" can't be derived from `state` alone once admin-issued
invites (which never decrement quota) exist alongside normal ones — without
it, voiding an admin-issued invite would incorrectly hand the attributed
user a free quota point they never spent.

`User` gains:

```python
invite_quota_remaining: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
invites_sent: Mapped[list[Invite]] = relationship(
    "Invite", back_populates="inviter", cascade="all, delete-orphan",
)
```

The column default of `0` is only a DB-level fallback for direct inserts
that forget to set it; every real creation path (below) sets it explicitly
from `get_registration_config()["default_quota"]` (or an override), matching how
`Note`/`Notebook` fields are always set explicitly at creation rather than
relying on column defaults.

No migration step needed — same as the RBAC plan, this repo has no Alembic;
`create_schema`/`Base.metadata.create_all` picks up the new table and column
on next `setup_database`/`reset_db` run.

## `src/assistant/invites/exceptions.py` (new)

```python
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
```

## `src/assistant/invites/service.py` (new)

```python
def default_quota_for_new_user(config: RegistrationConfig, override: int | None) -> int:
    """override if given, else config's default_quota."""
    return override if override is not None else config["default_quota"]


def create_invite(session: Session, inviter: User, invitee_email: str, config: RegistrationConfig) -> Invite:
    """Create a new pending invite, consuming one unit of the inviter's quota.

    Raises InvitesDisabledError if invites_enabled is false.
    Raises QuotaExhaustedError if inviter.invite_quota_remaining <= 0.
    Always creates a new row — re-inviting an already-pending email is
    never idempotent (the recipient may have lost the original link).
    Does NOT check whether invitee_email already has a User — an invite to
    an already-registered address is harmless (it will simply never
    convert; nothing surfaces it as an error) and re-checking here would
    just be a second copy of the uniqueness logic register_user already
    owns.
    """


def admin_create_invite(session: Session, inviter: User, invitee_email: str, config: RegistrationConfig) -> Invite:
    """Same as create_invite but bypasses invites_enabled AND quota
    entirely (quota_consumed=False) — CLI ways cannot be disabled, per spec."""


def get_valid_pending_invite(session: Session, invite_id: uuid.UUID, config: RegistrationConfig) -> Invite:
    """Raises InvitesDisabledError if invites_enabled is false (kill switch
    covers redemption too). Raises InviteNotUsableError if the id doesn't
    exist, isn't PENDING, or now() > expires_at."""


def convert_invite(session: Session, invite_id: uuid.UUID) -> None:
    """Mark PENDING -> CONVERTED. No quota refund — this is a successful spend."""


def void_invite(session: Session, actor: User, invite_id: uuid.UUID) -> None:
    """Sender-initiated void. Raises InvitePermissionError if actor is not
    the invite's inviter. No-ops (does not raise) if already non-pending —
    'void a not-converted invite' is idempotent from the sender's POV.
    Refunds quota iff quota_consumed."""


def admin_void_invite(session: Session, invite_id: uuid.UUID) -> None:
    """Force-void regardless of sender. Same refund rule as void_invite."""


def delete_invite(session: Session, invite_id: uuid.UUID) -> None:
    """Permanently remove an Invite row — admin-only erasure, distinct from
    void (a lifecycle transition that keeps the row for the sender's
    history). No-ops if the id doesn't exist.

    If the invite is still PENDING and quota_consumed, refunds the
    inviter's quota first (the same rule void_invite applies) — otherwise
    a still-live invite could be erased out from under its sender, leaving
    them down a quota point with no row left to explain why or to void for
    the refund. VOID/CONVERTED invites are erased with no quota side
    effect, matching what void_invite/convert_invite already settled.

    The recipient-facing behavior of a deleted invite is identical to a
    voided one — get_valid_pending_invite raises the same
    InviteNotUsableError either way, so deleting a still-pending invite is
    not a new failure mode for whoever's holding the link, only for the
    sender's own history/bookkeeping.
    """


def replenish_quota(session: Session, user: User, amount: int) -> None:
    """user.invite_quota_remaining += amount. Adds a delta, never sets
    an absolute value — an admin blind-replenishing can't accidentally
    lower someone's quota by not checking their current balance first."""


def on_user_created(
    session: Session, user: User, *, used_invite_id: uuid.UUID | None = None,
) -> None:
    """Called by every user-creation path after the User row is flushed.

    If used_invite_id is given, converts that specific invite. Then, for
    ALL other PENDING invites addressed to user.email (case-insensitive,
    any sender), voids and refunds each — this is the one shared
    implementation of 'any account creation for this email kills every
    other pending invite for it', covering both the normal
    accept-one-invite-voids-the-rest case and the race where the email got
    registered a different way while an invite was still pending.
    """
```

`get_valid_pending_invite`'s email-comparison caller (`register_user`, see
below) does `invite.invitee_email.lower() == email.lower()` itself — kept
out of this function since it's about registration-time validation, not
invite validity per se.

## `src/assistant/notes/user_service.py`

```python
def create_user(
    session: Session,
    email: str,
    firstname: str,
    lastname: str,
    *,
    invite_quota: int | None = None,
) -> User:
    config = Config().get_registration_config()
    user = User(
        email=email,
        firstname=firstname,
        lastname=lastname,
        invite_quota_remaining=default_quota_for_new_user(config, invite_quota),
    )
    session.add(user)
    session.flush()
    on_user_created(session, user)
    return user
```

This is the generic `POST /user` path (and, transitively, any admin
CLI/script that creates a user this way) — it now also gets a starting
quota and triggers the cascade-void rule, per the "applies to every
creation path" decision. It never takes an `invite_id` (there's no
invite-acceptance flow through this endpoint — that's `/auth/register`'s
job).

```python
def delete_user(session: Session, uid: uuid.UUID) -> User:
    """Permanently delete a user and everything that cascades from them.

    Raises UserNotFoundError if uid doesn't exist. Returns the deleted
    User (detached) so the caller can report what was removed before it's
    gone.

    Relies entirely on the cascade="all, delete-orphan" relationships
    already declared on User — no manual cleanup needed:
      - notebooks: every Notebook this user owns, which in turn cascades
        (via Notebook.entitlements) to every Entitlement on those
        notebooks, including ones held by OTHER users who had access.
      - notes: same, for notes owned directly.
      - entitlements: every Entitlement this user HOLDS as principal —
        their access to their own and others' notebooks/notes.
      - credentials, refresh_tokens: their login state.
      - invites_sent: every Invite they sent (regardless of state).

    This is a wide blast radius by design — deleting a user deletes their
    owned content outright, not just their membership in it. It does NOT
    touch Invite rows where this user's email is the invitee (that's a
    plain string field, not an FK) — a pending invite addressed to a
    deleted user's email is left as-is; nothing links it to the User row
    being removed.
    """
```

`session.delete(user); session.flush()` is the entire implementation —
this function exists to give CLI/API callers a single, permission-checked
entrypoint rather than each caller reaching for `session.delete` directly,
matching how every other mutation in this codebase goes through a service
function (`AGENTS.md`'s API Layer convention).

## `src/assistant/auth/service.py`

```python
def register_user(
    session: Session,
    *,
    email: str,
    password: str,
    firstname: str,
    lastname: str,
    invite_id: uuid.UUID | None = None,
) -> User:
    """Create a user and a password credential.

    Raises RegistrationDisabledError if registration_enabled is false and
    no invite_id was given. Raises InvitesDisabledError / InviteNotUsableError
    / InviteEmailMismatchError per get_valid_pending_invite and the
    email-match check, when an invite_id is given.
    """
    config = Config().get_registration_config()
    invite = None
    if invite_id is not None:
        invite = get_valid_pending_invite(session, invite_id, config)
        if invite.invitee_email.lower() != email.lower():
            raise InviteEmailMismatchError(invite_id)
    elif not config["registration_enabled"]:
        raise RegistrationDisabledError

    user = User(
        email=email,
        firstname=firstname,
        lastname=lastname,
        invite_quota_remaining=default_quota_for_new_user(config, None),
    )
    session.add(user)
    session.flush()

    credential = Credential(
        user_id=user.uid, provider="password", credential_hash=_ph.hash(password),
    )
    session.add(credential)
    session.flush()

    on_user_created(session, user, used_invite_id=invite_id)
    return user
```

Note the ordering: the registration-disabled/invite-validity checks happen
**before** anything is added to the session (same "check first, mutate
after" shape the RBAC plan used for permission checks), so a rejected
registration leaves nothing behind to roll back.

`register_user` importing from `assistant.invites` is a new
`auth -> invites` edge; `invites` imports nothing from `auth`, so no cycle.

## `src/assistant/api/routes/auth.py`

`RegisterRequest` gains `invite_id: uuid.UUID | None = None`
(`api/schemas/auth.py`). The route:

```python
@router.post("/register", status_code=201, response_model=UserResponse)
def register(body: RegisterRequest, session: SessionDep, request: Request, response: Response) -> UserResponse:
    try:
        user = register_user(
            session,
            email=body.email,
            password=body.password,
            firstname=body.firstname,
            lastname=body.lastname,
            invite_id=body.invite_id,
        )
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Email already registered") from exc

    access, refresh = issue_tokens(session, user.uid)
    _set_auth_cookies(request, response, access, refresh)
    return UserResponse.model_validate(user)
```

This is the fix for the pre-existing "register doesn't log in" gap —
identical to what `login` already does, called right after user creation
succeeds. `InvitesError` subclasses are **not** caught here individually;
they propagate to the global handlers registered in `api/exceptions.py`
(below), same as `PermissionDeniedError`/`UserNotFoundError` do today.

## `src/assistant/api/exceptions.py`

Five new handlers, same shape as the existing ones:

| Exception | Status |
|---|---|
| `InviteNotUsableError` | 404 |
| `InviteEmailMismatchError` | 422 |
| `InvitesDisabledError` | 403 |
| `RegistrationDisabledError` | 403 |
| `QuotaExhaustedError` | 403 |
| `InvitePermissionError` | 403 |

`InviteNotUsableError` → 404 is what makes the public validity-check
endpoint and a failed invite-based registration both naturally produce the
same generic "not found"-shaped response the frontend renders as "no
longer valid" — no special-casing needed in the route.

## API layer (`src/assistant/api/routes/invites.py`, new)

```
GET    /invites/config                 -> {registration_enabled, invites_enabled}   (public, no auth)
GET    /invites/{invite_id}/public     -> {valid: bool, email: str | None}          (public, no auth)
POST   /invites                        body: {invitee_email}  -> InviteResponse (201)
GET    /invites                        -> list[InviteResponse]   (caller's own, pending + history)
DELETE /invites/{invite_id}            -> 204                    (void, caller must be sender)
```

`InviteResponse` includes a computed `url` field, built by
`invites.service.build_invite_url` fresh in the route handler on every
response — this is the entire implementation of "regenerate" (see Decisions
recap); there is no separate regenerate endpoint.

```python
def build_invite_url(invite_id: uuid.UUID, config: Config) -> str:
    """https://{domain}:{port}/invite/{id} — recomputed fresh every read,
    never stored. Depends on config.get_domain() (raises if unset, same
    as the email service) and config.get_port() (defaults to 8000)."""
    return f"https://{config.get_domain()}:{config.get_port()}/invite/{invite_id}"


class InviteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    invitee_email: str
    state: InviteState
    created_at: datetime
    expires_at: datetime
    url: str  # populated by the route via build_invite_url, not from_attributes
```

`GET /invites/config` and `GET /invites/{id}/public` take no
`CurrentUserId` dependency — they're the two endpoints an anonymous visitor
(the invite recipient, or the pre-login frontend deciding whether to show a
"Register"/"Invite-only" link) needs to hit before any auth exists.

`UserResponse` (`api/schemas/users.py`) and auth's `UserResponse`
(`api/schemas/auth.py` — these are two separate classes today, same shape)
both gain `invite_quota_remaining: int`, so `/auth/me` and `/user/{uid}`
surface the quota without a dedicated endpoint.

`UserCreate` gains `invite_quota: int | None = None`, threaded into
`create_user_endpoint` → `create_user(..., invite_quota=body.invite_quota)`.

`app.py`: `app.include_router(invites_router, prefix="/invites",
tags=["invites"])`.

## CLI

**`src/assistant/cli/manage_invites.py`** (new) — direct DB session via
`get_session_factory()`, same shape as `add_evernote.py`
(`session_factory()` context manager + explicit `session.commit()`), not
`api_client.py`'s HTTP-client shape — there is no HTTP-reachable admin
identity to authenticate as, so this must run in-process against the DB,
authorized purely by whoever has shell access to run it (matching
`setup_database.py`/`reset_db.py`'s precedent).

```python
parser = argparse.ArgumentParser(...)
sub = parser.add_subparsers(dest="command", required=True)

create = sub.add_parser("create")
create.add_argument("--as", dest="sender_email", required=True)
create.add_argument("--to", dest="invitee_email", required=True)
create.set_defaults(func=cmd_create)

void = sub.add_parser("void")
void.add_argument("--id", dest="invite_id", required=True, type=uuid.UUID)
void.set_defaults(func=cmd_void)

replenish = sub.add_parser("replenish")
replenish.add_argument("--email", dest="user_email", required=True)
replenish.add_argument("--amount", dest="amount", required=True, type=int)
replenish.set_defaults(func=cmd_replenish)

delete = sub.add_parser("delete")
delete.add_argument("--id", dest="invite_id", required=True, type=uuid.UUID)
delete.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
delete.set_defaults(func=cmd_delete)
```

Each `cmd_*` opens `session_factory()`, calls the matching
`invites.service` function (`admin_create_invite`/`admin_void_invite`/
`replenish_quota`/`delete_invite`), prints a one-line confirmation, and
commits. `cmd_create` looks up the sender via `get_user_by_email` first — a
`UserNotFoundError` there is left to propagate and crash with a traceback,
same as every other CLI script in this repo (none of them catch
service-layer errors gracefully; `setup_database.py`'s `try/except
Exception: logger.exception; return 1` wrapper only covers unexpected
failures, not expected-domain-error UX).

`cmd_delete` is the one exception to "no confirmation needed, shell access
is the authorization" — permanent row deletion is irreversible in a way
`void`/`replenish` aren't (both are just state on a row that still exists
and could be manually fixed up), so without `--yes` it prints the invite's
`invitee_email`/`state`/`inviter` and prompts `y/N` before calling
`delete_invite`. `--yes` skips the prompt for scripted use.

**`src/assistant/cli/delete_user.py`** (new) — same direct-DB-session
shape as `manage_invites.py`. Single positional-ish operation, no
subparsers needed:

```python
parser.add_argument("--email", dest="email", required=True)
parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
```

Looks the user up via `get_user_by_email`, then — unless `--yes` — prints
a summary of the blast radius before deleting: count of owned notebooks,
count of owned notes, count of entitlements held, count of invites sent,
and prompts `y/N`. On confirmation, calls `user_service.delete_user` and
commits. This is the highest-blast-radius operation in this plan (see the
`delete_user` docstring above — it cascades through owned notebooks/notes
and everyone else's entitlements on them, not just this user's own data),
so the confirmation step is not optional-by-convention the way it might be
for a lower-stakes script — `--yes` exists only for scripted/tested use,
not as the expected default path for a human running this by hand.

**`src/assistant/cli/api_client.py`**: `cmd_create_user` gains
`--invite-quota` (optional int), forwarded as `invite_quota` in the POST
body — this one *does* go over HTTP, unlike `manage_invites.py`, because
it's exercising the already-public `POST /user` endpoint, not doing
anything that endpoint can't already do.

## Frontend

`types/index.ts`:

```ts
export interface Invite {
  id: string;
  invitee_email: string;
  state: 'pending' | 'void' | 'converted';
  created_at: string;
  expires_at: string;
  url: string;
}

export interface InvitesConfigFlags {
  registration_enabled: boolean;
  invites_enabled: boolean;
}
```

`User` gains `invite_quota_remaining: number`.

`api/invites.ts` (new):

```ts
export function fetchInvitesConfig(): Promise<InvitesConfigFlags> { ... }        // GET /invites/config
export function fetchInvitePublic(id: string): Promise<{ valid: boolean; email: string | null }> { ... }
export function createInvite(invitee_email: string): Promise<Invite> { ... }     // POST /invites
export function listInvites(): Promise<Invite[]> { ... }                          // GET /invites
export function voidInvite(id: string): Promise<void> { ... }                     // DELETE /invites/{id}
```

`api/auth.ts`: `RegisterPayload` gains `invite_id?: string`.

**Extract `components/RegistrationForm.tsx`** from the existing
`RegisterPage.tsx` body (firstname/lastname/email/password fields + submit),
parameterized by `emailLocked?: boolean` and `initialEmail?: string`, so the
email `<input>` renders `readOnly` and pre-filled when driven from an
invite. Both `RegisterPage` and the new `AcceptInvitePage` render this same
component — satisfying "distinct route, not a query param" (routing stays
separate) without duplicating the whole form markup.

**`pages/RegisterPage.tsx`** (edit): on mount, `useQuery` on
`fetchInvitesConfig()`; if `registration_enabled` is false, render "This
system is invite-only — ask someone for an invite link" instead of the
form (no form, no submit path — this is the page that used to be always
open). If true, renders `<RegistrationForm />` with no `invite_id`, same
submit flow as today plus the new field simply omitted.

**`pages/AcceptInvitePage.tsx`** (new), route `/invite/:inviteId`:
`useQuery` on `fetchInvitePublic(inviteId)`. If `!valid`: generic "This
invite is no longer valid" message + link to `/login`. If valid: banner
"You've been invited to join" + `<RegistrationForm initialEmail={email}
emailLocked invite_id={inviteId} />`, submitting through the same
`register()` call as `RegisterPage` (now carrying `invite_id`).

**`pages/InvitesPage.tsx`** (new), route `/invites` (protected): quota
display (`user.invite_quota_remaining`, from `useAuth()`), a compose
`<form>` (email input + "Send invite", `disabled` at zero quota) wired to a
`createInvite` mutation, a table of `state === 'pending'` invites (URL +
Void button) and a `<details>`-wrapped collapsible table of the rest —
matching `ShareDialog.tsx`'s existing `useQuery`/`useMutation` +
`queryClient.invalidateQueries` shape.

**`App.tsx`**: add `<Route path="/invite/:inviteId" element={<AcceptInvitePage />} />`
alongside `/login`/`/register` (public group); add `<Route path="/invites"
element={<Layout />} />`... actually `Layout` currently renders the
notebook/note shell unconditionally based on URL params, so `/invites`
instead gets its own top-level protected route rendering `InvitesPage`
directly inside `AuthProvider`, sibling to the `ProtectedRoutes` block, not
routed through `Layout`.

**`components/Layout.tsx`**: header gains an "Invites" nav link (only
rendered when `fetchInvitesConfig().invites_enabled` is true) next to the
existing user/logout block.

## Test plan

Following `AGENTS.md`'s TDD convention — module-level functions, `# ---
Section ---` separators.

**`tests/invites/test_service.py`** (new) — `db_session` fixture (SQLite,
matching `tests/notes/test_service.py`'s style) + `_make_user` helper.
Cases: `create_invite` decrements quota by exactly 1 and sets
`quota_consumed=True`; raises `QuotaExhaustedError` at 0; raises
`InvitesDisabledError` when config says so; two invites to the same
still-pending email from the same sender are both created (never
idempotent); `admin_create_invite` never touches quota and sets
`quota_consumed=False`; `get_valid_pending_invite` raises
`InviteNotUsableError` for missing/void/converted/expired, succeeds for
pending-and-unexpired; `convert_invite` transitions state, no quota change;
`void_invite` refunds iff `quota_consumed`, raises `InvitePermissionError`
for a non-sender, no-ops on an already-void/converted row;
`admin_void_invite` ignores sender identity; `replenish_quota` adds (not
sets) — call it twice and assert the sum; `on_user_created` with
`used_invite_id` converts that one and voids+refunds every other pending
invite for the same email including ones from other senders; without
`used_invite_id` (plain/CLI registration) still voids+refunds all pending
invites for that email; `delete_invite` on a PENDING+`quota_consumed`
invite refunds the inviter then removes the row (assert both the refund
and that a fresh query for the id returns nothing); on a VOID/CONVERTED
invite removes it with no quota change; on an unknown id is a no-op (no
exception).

**`tests/api/test_auth.py`** (extend) — registration-mode matrix: both
flags true → open registration succeeds and auto-logs-in (assert
`Set-Cookie` on the response, closing the pre-existing gap);
`registration_enabled=false`, no `invite_id` → 403
`RegistrationDisabledError`; same flag false but a valid `invite_id` →
succeeds; `invites_enabled=false` with a valid `invite_id` → 403
`InvitesDisabledError` (kill switch blocks redemption too); mismatched
email vs. invite → 422; expired/void/converted invite → 404 (indistinguishable
across the three); successful invite-registration leaves the invite
`converted` and refunds/voids sibling invites for that email.

**`tests/api/test_invites.py`** (new) — `client`/`test_user`/`auth_headers`
fixtures per `tests/api/conftest.py`, plus a second `other_user` pair.
`POST /invites` succeeds and decrements quota (assert via `GET
/auth/me`); 403 at zero quota; `GET /invites` returns only the caller's
own; `DELETE /invites/{id}` by a non-sender → 403, by the sender → 204 +
quota refunded; `GET /invites/{id}/public` for a real pending invite
returns `{valid: true, email}`; for void/converted/expired/unknown all
return `{valid: false, email: null}` with the same shape; `GET
/invites/config` reflects whatever the test app's config overrides say
(parametrize both flag combinations).

**`tests/cli/test_manage_invites.py`** (new) — matching whatever fixture
style `tests/cli/` already uses (confirm during implementation — likely a
`CliRunner`-style or direct `main()`-with-argv invocation plus a real
`db_session`). Cases: `create --as --to` creates an invite attributed to
the named sender with `quota_consumed=False` and no quota change; `void
--id` force-voids regardless of sender, refunds only if `quota_consumed`;
`replenish --email --amount` adds the delta (call twice, assert
cumulative); `delete --id --yes` removes the row outright (refunding
first if it was still pending and quota-consuming, per `delete_invite`);
`delete --id` without `--yes` prompts and does not delete on a `n`/default
response.

**`tests/cli/test_delete_user.py`** (new) — same style. Deleting a user
who owns notebooks/notes cascades away those notebooks/notes and every
entitlement on them, including ones held by a *different* user (assert
that other user's entitlement row is also gone); deleting a user who sent
invites removes those invite rows too (via `invites_sent` cascade); an
invite where the deleted user was only the *invitee* (email match, no FK)
is left untouched — assert it's still there afterward; unknown `--email`
propagates `UserNotFoundError`; without `--yes`, a `n`/default prompt
response leaves the user in place.

**`tests/test_config.py`** (extend) — `get_registration_config()` returns
the documented defaults when `registration:` is absent from YAML; each of
the four keys individually overridable via its `REGISTRATION_*` env var,
matching the existing per-key override tests for other config sections;
`get_port()` defaults to `8000` and is overridable via `PORT`.

**Frontend** `InvitesPage.test.tsx` (new): renders quota + pending/history
tables; submitting the compose form calls `createInvite`; a 403 response
renders "no invites remaining"; clicking Void calls `voidInvite`; compose
form's submit button is `disabled` when quota is 0. `AcceptInvitePage.test.tsx`
(new): valid invite renders the locked-email form; invalid renders the
generic message; successful submit navigates to `/notebooks` (same as
`RegisterPage` today). `RegisterPage.test.tsx` (extend, if it exists —
confirm during implementation): `registration_enabled=false` renders the
invite-only message instead of the form.

## Build order

1. Config (`config.py`: `RegistrationConfig` + `get_registration_config` +
   top-level `port` + `get_port`). Extend
   `tests/test_config.py` first (TDD).
2. Schema (`schema.py`: `InviteState`, `Invite`, `User.invite_quota_remaining`
   + `invites_sent`). Sanity-check with `pytest tests/models` — expect no
   failures, this is additive.
3. `invites/exceptions.py`, then TDD `tests/invites/test_service.py` →
   `invites/service.py`. Depends on 1-2, independent of everything else.
4. `notes/user_service.py::create_user` gains `invite_quota` +
   `on_user_created` call. Depends on 3.
5. `auth/service.py::register_user` gains `invite_id` + the gate + `convert_invite`
   + `on_user_created`. Depends on 3. Extend `tests/api/test_auth.py` per the
   matrix above (TDD against the service function directly first if this
   repo has a unit-level auth-service test file, else go straight to the API
   test — confirm which during implementation).
6. `api/exceptions.py` (five new handlers) + `api/schemas/{auth,users,invites}.py`
   + `api/routes/auth.py` (invite_id passthrough + auto-login) +
   `api/routes/invites.py` (new) + `app.py` (mount). TDD against
   `tests/api/test_auth.py` (extended) and the new `tests/api/test_invites.py`.
   Depends on 4-5.
7. CLI: `manage_invites.py` (new, including `delete`) + `delete_user.py`
   (new) + `api_client.py`'s `--invite-quota`. TDD against
   `tests/cli/test_manage_invites.py` and `tests/cli/test_delete_user.py`.
   Depends on 3-4.
8. Frontend: types, `api/invites.ts`, `RegistrationForm` extraction,
   `RegisterPage` edit, `AcceptInvitePage`, `InvitesPage`, `App.tsx` routes,
   `Layout.tsx` nav link. Depends on 6 (needs the real API shape). TDD
   against the new/extended `*.test.tsx` files.
9. `make check` (backend) + `make frontend-check` + `make frontend-test`
   across everything touched.

## Verification

- `make check` passes (mypy strict, ruff, full pytest suite).
- `make frontend-check && make frontend-test` pass.
- Manual smoke test: `make services-up`, `python -m assistant.cli.setup_database`,
  register user A openly; as A, send an invite to `b@example.com`, confirm
  quota drops by 1 and the pending table shows the URL; open that URL in an
  incognito window, confirm the email is locked, register as B, confirm B
  lands logged into `/notebooks` and A's invite now shows `converted`;
  flip `registration.registration_enabled: false` in `config.yaml`, restart
  the API, confirm `/register` now shows the invite-only message and a
  direct `POST /auth/register` without `invite_id` 403s, while a fresh
  invite from A still works end to end; flip
  `registration.invites_enabled: false` too and confirm that same fresh
  invite's URL now fails; run `python -m assistant.cli.manage_invites
  create --as a@example.com --to c@example.com`, confirm it works even
  with `invites_enabled: false` and doesn't touch A's quota; `replenish` A
  and confirm `/auth/me` reflects it; `python -m assistant.cli.manage_invites
  delete --id <id>` on a still-pending invite, confirm the prompt, confirm
  the refund, and confirm the id 404s from `GET /invites/{id}/public`
  afterward; `python -m assistant.cli.delete_user --email b@example.com`,
  confirm B's notebooks/notes/entitlements are gone and B can no longer
  log in.

## Out of scope

- Emailing the invite link (still delivered out of band by whoever sends
  it) — no mail-sending integration exists in this codebase.
- Any interaction with the note/notebook RBAC entitlement system
  (`docs/specs/0003_role_based_access_control.md`) — fully separate feature,
  confirmed during grilling.
- A background expiry sweep — expiry is checked lazily wherever an invite
  is read, per the spec.
- Rate-limiting invite creation beyond the quota itself.
- Bulk/scripted deletion (e.g. "delete all expired invites," "delete all
  users matching X") — both new CLI commands operate on one row/user at a
  time, by id/email.
- Cleaning up `Invite` rows where a deleted user was only the *invitee*
  (matched by email string, not FK) — `delete_user` only cascades what's
  actually linked to the `User` row by foreign key.
- An in-app admin role/permission system — the CLI's authorization model is
  "has shell access to the server," matching every other admin-shaped
  script in this repo.

## Further notes

- `notes/user_service.py` gains a new import from `assistant.invites` —
  directionally fine (`invites` imports nothing from `notes` or `auth`), but
  worth flagging since it's a new module boundary in a codebase that
  previously had `notes`/`auth` as siblings with no cross-imports between
  them.
- `UserResponse` exists as two separate, identically-shaped Pydantic classes
  today (`api/schemas/auth.py` and `api/schemas/users.py`). This plan edits
  both rather than unifying them — de-duplicating them is a pre-existing
  wart, not something to fold into this change.
