# Implementation plan: Google OpenID Connect authentication

Implements Google OIDC login/registration per the decisions reached in the
`/grill-me` session on the original request. Follows Google's documented
flow starting from the ["Authenticating the
user"](https://developers.google.com/identity/openid-connect/openid-connect#authenticatingtheuser)
section: authorization-code flow, backend-side code exchange, ID-token
validation. The Google Cloud Console side (OAuth client, consent screen,
authorized redirect URI) is the user's own responsibility — out of scope
here.

## Context

`credentials` (`src/assistant/models/schema.py:160-188`, `Credential`)
already has `provider` and `provider_subject` columns plus a
`UniqueConstraint("provider", "provider_subject", ...)` — added ahead of
time for exactly this feature, currently unused (`provider="password"` is
the only row that exists today). **No schema migration is needed.**

Today there is one identity provider (`password`,
`src/assistant/auth/service.py`) and one gate for minting a `User`
(`invites.service.resolve_registration_gate`, reused by both
`auth.service.register_user` and `notes.user_service.create_user`). Both
of those two functions currently duplicate the same five-line sequence
inline — load `get_registration_config()`, call
`resolve_registration_gate`, build the `User` with
`default_quota_for_new_user`, flush, call `on_user_created`. Adding a
third caller (Google) by copy-pasting that sequence a third time would
make the duplication actively worse, so this plan first extracts it into
one shared `invites.service.create_gated_user`, then has all three
callers (`register_user`, `create_user`, and the new
`google_auth.service.handle_google_callback`) call that instead of
inlining it — see the `invites/service.py` section below.

`docs/architecture/authentication.md`'s existing "Google OAuth2" /
"Provider Linking" sections (`:69-91`, `:182-186`) describe an
auto-linking design (re-enter your password to link a Google identity to
an existing password account, replacing the password credential). That
was explicitly never built and conflicts with this session's decision
(one mechanism per user for now, collisions are rejected, linking is
future work) — this plan rewrites those sections rather than implementing
what they describe.

Two more pre-existing things surfaced during grilling and are addressed
as side effects, scoped narrowly (see "Further notes" for why each is
scoped the way it is, not wider):

- No email-confirmation flow exists anywhere in this system today —
  nothing to preserve or skip. Google's own `email_verified` claim is
  checked at auth time as a gate, not persisted anywhere.
- `PATCH /user/{uid}` (`src/assistant/api/routes/users.py:56-68`) has no
  authentication dependency at all — anyone can rename or re-email any
  user by UID. This becomes load-bearing once a Google user is expected
  to fix up a missing name via this endpoint, so it's hardened here.

## Decisions recap (from grilling)

- **Matching**: `(Credential.provider="google", Credential.provider_subject=<Google `sub`>)`
  is the durable lookup for a returning Google user — never email, since
  email isn't guaranteed stable.
- **Auto-provision, same gate as everyone else**: an unrecognized Google
  identity is auto-registered (no separate "login vs. register" UX for
  Google — one button, one backend flow), but it still goes through
  `resolve_registration_gate`: `registration_enabled=false` and no
  invite → rejected; an invite → must be valid and match Google's email
  exactly, or rejected.
- **Collision**: if the Google email already belongs to a *different*
  provider's credential (i.e. a password account), reject with an
  actionable error. No auto-linking — deferred to a future
  "switch/link mechanism" feature.
- **Email verification**: Google's `email_verified` claim must be `true`
  or the attempt is rejected outright. No confirmation-email fallback —
  none exists in this system, and building one is explicitly out of
  scope ("will be built another day").
- **Missing name claims**: `given_name`/`family_name` aren't guaranteed
  present. If absent, the account is still created with an empty string
  for that field (satisfies the `NOT NULL` columns) — no blocking
  "complete your profile" step. Editable later via `PATCH /user/{uid}`;
  **no frontend UI for that edit is built in this plan** (explicitly
  out of scope per the session).
- **OAuth mechanics**: backend owns both ends of the round trip.
  `GET /auth/google` (optional `?invite_id=`) builds a signed `state`
  and redirects to Google; `GET /auth/google/callback` exchanges the
  code, verifies the ID token, and redirects again (never returns JSON —
  see "Callback response shape" below). Scopes `openid email profile`;
  `prompt=select_account`. Web/cookie mode only, no bearer/native path.
- **State carries the round trip**: no server-side session exists to
  stash CSRF/replay state, so `{nonce, invite_id?, exp}` is signed
  (HMAC, same secret as access tokens) and passed as `state` — Google
  echoes it back verbatim on the callback.
- **Invite UX**: `/invite/:inviteId` shows "Continue with Google"
  immediately, no email typing required — Google supplies the email,
  the backend validates it against the invite server-side.
- **Config**: mirrors the Mailgun pattern — non-secret fields in
  `config.yaml` under `google:`, `GOOGLE_CLIENT_SECRET` env-only, both
  through a typed `Config.get_google_config()`. The redirect URI itself
  is **not** stored as a full URL — only a relative `redirect_path` is
  configured; the full URI is composed from the existing top-level
  `domain`/`port` config, the same way `invites.service.build_invite_url`
  already composes invite links (added after the initial plan draft, per
  follow-up feedback — see the Config section below).
- **`/user` hardening, narrowed from the original ask**: grilling's Q17
  assumed `POST /user` bypasses registration gating entirely; reading
  `notes/user_service.py:24-51` during planning shows that's wrong —
  `create_user` already calls `resolve_registration_gate`, same as
  `register_user`. The actual, still-real gap is narrower: neither
  `POST /user` nor `PATCH /user/{uid}` requires authentication at all.
  This plan fixes only `PATCH` (add `CurrentUser`, self-only) because
  that's the endpoint this feature makes load-bearing. `POST /user`'s
  lack of auth is left alone — see "Further notes".

## New/changed files

- `src/assistant/config.py` — edit. `GoogleConfig` TypedDict +
  `AssistantConfig.google` + `Config.get_google_config()`.
- `config.yaml` — edit. New `google:` section (client id + redirect URI;
  the secret is env-only, documented but not set here, same convention
  as `mailgun.apikey`).
- `pyproject.toml` — edit. Add `google-auth` to `[project.dependencies]`
  (ID-token verification against Google's JWKS). Code exchange itself
  uses the already-present `requests`, matching `email/service.py`'s
  pattern — no new HTTP client library needed.
- `src/assistant/auth/service.py` — edit. Rename `_jwt_secret` →
  `jwt_secret` (drop the leading underscore, no behavior change) so
  `google_auth.state` can sign/verify with the same secret without
  reaching into a private name. `register_user` shrinks to a thin
  wrapper around the new `invites.service.create_gated_user` (see
  below) plus its own password-`Credential` creation.
- `src/assistant/invites/service.py` — edit. New `create_gated_user`,
  factored out of the identical sequence `auth.service.register_user`
  and `notes.user_service.create_user` each inline today — see the
  dedicated section below.
- `src/assistant/notes/user_service.py` — edit. `create_user` shrinks to
  a thin wrapper around `create_gated_user`, same as `register_user`.
- `src/assistant/google_auth/__init__.py`, `.../exceptions.py`,
  `.../state.py`, `.../oauth.py`, `.../service.py` — new module, peer to
  `assistant.auth`/`assistant.invites`. `service.py`'s
  `handle_google_callback` is the third caller of `create_gated_user`.
- `src/assistant/api/routes/auth.py` — edit. Two new routes,
  `GET /google` and `GET /google/callback`, on the existing `/auth`
  router (matches the paths `docs/architecture/authentication.md`
  already sketched as `GET /auth/google` / `POST /auth/google/callback`
  — this plan makes the callback a `GET`, since Google's redirect is
  always a GET with `code`/`state` query params, not a POST).
- `src/assistant/api/routes/users.py` — edit. `update_user_endpoint`
  gains `CurrentUser`, self-only enforcement.
- `docs/architecture/authentication.md` — edit. Rewrite "Google OAuth2"
  and "Provider Linking" to match what's actually built; update the
  data-model comment on `Credential.provider` (`"password, google"` is
  already accurate, no change needed there).
- Frontend: `frontend/src/api/client.ts` (edit, export `apiUrl`),
  `frontend/src/components/GoogleAuthButton.tsx` (new),
  `frontend/src/components/RegistrationForm.tsx` (edit — embed the
  button), `frontend/src/pages/LoginPage.tsx` (edit — embed the button +
  render `google_error`), `frontend/src/pages/AcceptInvitePage.tsx`
  (edit — render `google_error`), `frontend/src/lib/googleAuthErrors.ts`
  (new).
- Tests: `tests/google_auth/test_state.py`, `.../test_oauth.py`,
  `.../test_service.py` (new), `tests/api/test_auth.py` (extend),
  `tests/api/test_users.py` (extend — `TestUpdateUser` needs auth
  headers now), `tests/test_config.py` (extend); frontend
  `GoogleAuthButton.test.tsx` (new), `RegistrationForm.test.tsx` (new —
  didn't exist before), `LoginPage.test.tsx` / `AcceptInvitePage.test.tsx`
  (extend, both already exist).

## Config (`src/assistant/config.py`, `config.yaml`)

```python
class GoogleConfig(TypedDict):
    """Google OAuth2/OIDC configuration."""

    client_id: str
    client_secret: str
    redirect_path: str


class AssistantConfig(TypedDict, total=False):
    ...
    google: GoogleConfig
```

```python
def get_google_config(self) -> GoogleConfig:
    """Get the effective Google OAuth2 configuration.

    Env var overrides follow the module convention:
        - `google.client_id`     -> `GOOGLE_CLIENT_ID`
        - `google.client_secret` -> `GOOGLE_CLIENT_SECRET`
        - `google.redirect_path` -> `GOOGLE_REDIRECT_PATH`

    `redirect_path` is not a full URL — it's appended to
    `https://{domain}:{port}` (this app's existing top-level config,
    already used the same way by invites.service.build_invite_url) to
    form the URI registered with Google. Defaults to
    `/auth/google/callback`, matching this plan's own route.

    Raises:
        ValueError: if `client_id` or `client_secret` is missing from
            both YAML and env. `redirect_path` always has a default.
    """
    client_id = self._get_typed_value(key="google.client_id", expected_type=str)
    client_secret = self._get_typed_value(key="google.client_secret", expected_type=str)
    redirect_path = self.get("google.redirect_path", "/auth/google/callback")

    missing_keys: list[str] = []
    if not client_id:
        missing_keys.append("client_id")
    if not client_secret:
        missing_keys.append("client_secret")
    if missing_keys:
        msg = f"Google configuration missing required keys: {', '.join(missing_keys)}"
        raise ValueError(msg)

    assert client_id is not None
    assert client_secret is not None
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_path": redirect_path,
    }
```

`config.yaml` addition:

```yaml
# Google OAuth2 (client_secret is always supplied via GOOGLE_CLIENT_SECRET env var).
# redirect_path is appended to https://{domain}:{port} (see `domain`/`port`
# above) to form the redirect URI you register in the Google Cloud Console.
google:
  client_id: replace-with-your-client-id.apps.googleusercontent.com
  # redirect_path: /auth/google/callback  # optional, this is the default
```

The composed `https://{domain}:{port}{redirect_path}` must be the exact
URL registered as an authorized redirect URI in the Google Cloud Console
entry the user sets up — it's the backend's own callback endpoint,
reachable directly (see "Callback response shape" below for why this is
*not* the frontend's origin).

## `src/assistant/google_auth/exceptions.py` (new)

```python
class GoogleAuthFlowError(Exception):
    """Base exception for the google_auth module."""


class GoogleStateInvalidError(GoogleAuthFlowError):
    """The `state` param is missing, malformed, unsigned, or expired."""


class GoogleTokenExchangeError(GoogleAuthFlowError):
    """The authorization-code exchange with Google's token endpoint failed."""


class GoogleTokenInvalidError(GoogleAuthFlowError):
    """The ID token failed signature/issuer/audience/expiry/nonce validation."""


class GoogleEmailNotVerifiedError(GoogleAuthFlowError):
    """Google reported email_verified=false for this identity."""


class GoogleAccountCollisionError(GoogleAuthFlowError):
    """This email already belongs to a different provider's credential."""

    def __init__(self, email: str) -> None:
        self.email = email
        super().__init__(f"{email} is already registered with a different provider")
```

## `src/assistant/google_auth/state.py` (new)

```python
"""Sign/verify the OAuth `state` param — the only place round-trip data
(the CSRF nonce and, for the invite flow, which invite) survives between
`GET /auth/google` and `GET /auth/google/callback`, since this backend
keeps no server-side session."""

STATE_TTL_MINUTES = 10


@dataclass(frozen=True)
class GoogleStateClaims:
    nonce: str
    invite_id: uuid.UUID | None


def sign_state(*, nonce: str, invite_id: uuid.UUID | None) -> str:
    payload = {
        "nonce": nonce,
        "invite_id": str(invite_id) if invite_id else None,
        "exp": datetime.now(UTC) + timedelta(minutes=STATE_TTL_MINUTES),
    }
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


def verify_state(raw: str) -> GoogleStateClaims:
    try:
        payload = jwt.decode(raw, jwt_secret(), algorithms=["HS256"])
    except jwt.InvalidTokenError as exc:
        raise GoogleStateInvalidError from exc
    invite_id = uuid.UUID(payload["invite_id"]) if payload.get("invite_id") else None
    return GoogleStateClaims(nonce=payload["nonce"], invite_id=invite_id)
```

`jwt_secret` imported from `assistant.auth.service` (the rename above).
Reusing the access-token secret for `state` is deliberate — it's a
second, independent use of the same HS256 signing key, not a new secret
to provision; a 10-minute TTL comfortably covers a human completing the
Google consent screen.

## `src/assistant/google_auth/oauth.py` (new)

All direct interaction with Google's endpoints, isolated here — nothing
else in the codebase talks to Google.

```python
@dataclass(frozen=True)
class GoogleIdTokenClaims:
    sub: str
    email: str
    email_verified: bool
    given_name: str | None
    family_name: str | None


def redirect_uri(config: Config) -> str:
    """The Google OAuth redirect URI, composed the same way
    invites.service.build_invite_url composes invite links: domain/port
    are this app's single public origin (config-wide, already used for
    invite URLs); only the path is Google-specific.

    Used both when building the authorization URL and when exchanging
    the code — Google requires the two to match exactly.
    """
    return f"https://{config.get_domain()}:{config.get_port()}{config.get_google_config()['redirect_path']}"


def build_authorization_url(*, state: str, nonce: str) -> str:
    """The URL to redirect the browser to for the consent screen.

    `prompt=select_account` forces the Google account chooser every time,
    so a shared/public machine with an existing Google session doesn't
    silently authenticate as the wrong person.
    """
    config = Config()
    google_config = config.get_google_config()
    params = {
        "client_id": google_config["client_id"],
        "redirect_uri": redirect_uri(config),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


def exchange_code_for_tokens(code: str) -> dict[str, str]:
    """POST the authorization code to Google's token endpoint.

    Raises GoogleTokenExchangeError on a network failure or a non-2xx
    response. No retry (unlike email/service.py's send_email) — this is
    a synchronous step in an interactive request, not a background job;
    on failure the user just clicks the button again.
    """
    config = Config()
    google_config = config.get_google_config()
    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": google_config["client_id"],
                "client_secret": google_config["client_secret"],
                "redirect_uri": redirect_uri(config),
                "grant_type": "authorization_code",
            },
            timeout=10,
        )
    except requests.RequestException as exc:
        raise GoogleTokenExchangeError(str(exc)) from exc
    if not response.ok:
        msg = f"Google token endpoint returned {response.status_code}: {response.text}"
        raise GoogleTokenExchangeError(msg)
    return response.json()


def verify_id_token(raw_id_token: str, *, expected_nonce: str) -> GoogleIdTokenClaims:
    """Verify signature (against Google's JWKS), issuer, audience, and
    expiry via `google-auth`, then check the nonce ourselves (the library
    doesn't take a nonce param).

    Raises GoogleTokenInvalidError for any of: bad signature, wrong
    issuer/audience, expired token, or a nonce that doesn't match what
    google_auth.state signed for this attempt (replay protection).
    """
    config = Config().get_google_config()
    try:
        claims = google_id_token.verify_oauth2_token(
            raw_id_token, google_requests.Request(), audience=config["client_id"],
        )
    except (GoogleAuthError, ValueError) as exc:
        raise GoogleTokenInvalidError(str(exc)) from exc
    if claims.get("nonce") != expected_nonce:
        raise GoogleTokenInvalidError("nonce mismatch")
    return GoogleIdTokenClaims(
        sub=claims["sub"],
        email=claims["email"],
        email_verified=bool(claims.get("email_verified", False)),
        given_name=claims.get("given_name"),
        family_name=claims.get("family_name"),
    )
```

(`google_id_token` = `google.oauth2.id_token`, `google_requests` =
`google.auth.transport.requests`, `GoogleAuthError` =
`google.auth.exceptions.GoogleAuthError` — aliased on import to keep
`Google*` names visually distinct from this module's own exception
classes.)

## `src/assistant/invites/service.py` (`create_gated_user`, edit)

`register_user` and `create_user` each inline the same sequence today:
load `get_registration_config()`, call `resolve_registration_gate`,
build the `User` (quota via `default_quota_for_new_user`), flush, call
`on_user_created`. Adding Google as a third, independent copy of that
sequence is what prompted pulling it out — one function, three thin
callers:

```python
def create_gated_user(
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
```

`auth/service.py::register_user` shrinks to:

```python
def register_user(
    session: Session, *, email: str, password: str, firstname: str, lastname: str,
    invite_id: uuid.UUID | None = None,
) -> User:
    """Create a user and a password credential. See create_gated_user
    for the registration-gate/quota/invite-conversion behavior."""
    user, _invite = create_gated_user(
        session, email=email, firstname=firstname, lastname=lastname, invite_id=invite_id,
    )
    credential = Credential(
        user_id=user.uid, provider="password", credential_hash=_ph.hash(password),
    )
    session.add(credential)
    session.flush()
    return user
```

`notes/user_service.py::create_user` shrinks to:

```python
def create_user(
    session: Session, email: str, firstname: str, lastname: str, *,
    invite_quota: int | None = None, invite_id: uuid.UUID | None = None,
) -> User:
    """The generic POST /user path — no Credential, matching today's
    behavior (a user created this way can't log in via any provider
    until one is added separately)."""
    user, _invite = create_gated_user(
        session, email=email, firstname=firstname, lastname=lastname,
        invite_id=invite_id, invite_quota_override=invite_quota,
    )
    return user
```

Both are pure refactors — same signature, same behavior, same raised
exceptions — so the existing test suites for both
(`tests/api/test_auth.py`'s registration matrix,
`tests/api/test_users.py`'s `TestCreateUser`) should pass unmodified and
serve as the regression check; see Test plan.

## `src/assistant/google_auth/service.py` (new)

```python
def handle_google_callback(
    session: Session,
    *,
    claims: GoogleIdTokenClaims,
    invite_id: uuid.UUID | None,
) -> User:
    """Login-or-register from a verified Google ID token.

    Raises GoogleEmailNotVerifiedError if claims.email_verified is false.
    Raises GoogleAccountCollisionError if this email belongs to a
    different provider's credential.
    For a not-yet-seen identity, delegates to
    invites.service.create_gated_user — identical gate, quota, and
    invite-conversion behavior as password registration
    (RegistrationDisabledError / InvitesDisabledError /
    InviteNotUsableError / InviteEmailMismatchError all propagate
    uncaught, same as register_user).
    """
    if not claims.email_verified:
        raise GoogleEmailNotVerifiedError

    existing_credential = session.scalar(
        select(Credential).where(
            Credential.provider == "google",
            Credential.provider_subject == claims.sub,
        )
    )
    if existing_credential is not None:
        return get_user(session, existing_credential.user_id)

    existing_user = session.scalar(select(User).where(User.email == claims.email))
    if existing_user is not None:
        # A provider_subject match would have been caught above, so
        # reaching here means this email belongs to a *different*
        # provider (password, today) — collision, not a returning
        # Google user.
        raise GoogleAccountCollisionError(claims.email)

    user, _invite = create_gated_user(
        session,
        email=claims.email,
        firstname=claims.given_name or "",
        lastname=claims.family_name or "",
        invite_id=invite_id,
    )

    credential = Credential(
        user_id=user.uid, provider="google", provider_subject=claims.sub,
    )
    session.add(credential)
    session.flush()
    return user
```

The pre-creation checks (email-verified, existing-credential lookup,
collision) stay here rather than moving into `create_gated_user` — they're
specific to "is this a returning or colliding *Google* identity," a
question `create_gated_user` (which only ever creates brand-new users)
has no reason to know about.

## `src/assistant/api/routes/auth.py`

Two new routes on the existing router (still mounted at `/auth`):

```python
@router.get("/google")
def google_start(invite_id: uuid.UUID | None = None) -> RedirectResponse:
    nonce = secrets.token_urlsafe(16)
    state = sign_state(nonce=nonce, invite_id=invite_id)
    return RedirectResponse(build_authorization_url(state=state, nonce=nonce), status_code=302)


def _google_redirect(config: Config, path: str) -> RedirectResponse:
    """Absolute redirect back into the app, reusing the same domain/port
    composition invites.service.build_invite_url already uses — the
    frontend is co-hosted with the API in production, so this is the
    app's single public origin either way."""
    url = f"https://{config.get_domain()}:{config.get_port()}{path}"
    return RedirectResponse(url, status_code=302)


@router.get("/google/callback")
def google_callback(  # noqa: PLR0913
    session: SessionDep,
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    config = Config()

    def fail(path: str, error_code: str) -> RedirectResponse:
        return _google_redirect(config, f"{path}?google_error={error_code}")

    if error is not None:
        return fail("/login", "denied")
    if code is None or state is None:
        return fail("/login", "invalid_request")

    try:
        state_claims = verify_state(state)
    except GoogleStateInvalidError:
        return fail("/login", "invalid_state")

    fail_path = f"/invite/{state_claims.invite_id}" if state_claims.invite_id else "/login"

    try:
        tokens = exchange_code_for_tokens(code)
        id_claims = verify_id_token(tokens["id_token"], expected_nonce=state_claims.nonce)
    except (GoogleTokenExchangeError, GoogleTokenInvalidError):
        return fail(fail_path, "google_failed")

    try:
        user = handle_google_callback(
            session, claims=id_claims, invite_id=state_claims.invite_id,
        )
    except GoogleEmailNotVerifiedError:
        return fail(fail_path, "unverified_email")
    except GoogleAccountCollisionError:
        return fail(fail_path, "collision")
    except InviteEmailMismatchError:
        return fail(fail_path, "invite_email_mismatch")
    except (InviteNotUsableError, InvitesDisabledError, RegistrationDisabledError):
        return fail(fail_path, "registration_closed")

    access, refresh = issue_tokens(session, user.uid)
    _set_auth_cookies(request, response, access, refresh)
    return _google_redirect(config, "/notebooks")
```

### Callback response shape

`google/callback` never returns JSON — Google's redirect is a top-level
browser navigation, not something frontend JS reads a response body
from. Every outcome is an HTTP redirect: success sets the cookies (via
the existing `_set_auth_cookies` helper, unchanged) and sends the browser
to `/notebooks`; failure sends it to `/login` or, for an invite attempt,
back to `/invite/:inviteId`, with a short machine-readable
`?google_error=<code>` the frontend turns into a message. This is also
why these exceptions get **no** entry in `api/exceptions.py`'s global
JSON handlers (unlike `InviteNotUsableError` et al., which do, for the
JSON-API endpoints that share them) — they're caught right here and
turned into redirects instead.

`google_start`'s `redirect_uri` (via `oauth.redirect_uri`, composed from
`domain`/`port`/`google.redirect_path`) points at the backend's own
`/auth/google/callback` directly — Google has no way to reach a frontend
dev-server route, and nothing here proxies for it (`frontend/vite.config.ts`
only proxies `/files`). The *outgoing* success/failure redirect uses the
exact same `{domain}:{port}` composition — both the Google-facing
redirect URI and the browser-facing app URLs are built from the one
config-wide origin, the same one `invites.service.build_invite_url`
already uses for invite links, and for the same reason: in production
frontend and API are co-hosted behind one public origin, so this is
simply that origin. In local dev this inherits the exact same rough edge
invite links already have (the default `config.yaml` domain doesn't
resolve to a real dev frontend) — not a new problem this plan
introduces; a developer testing the full Google flow locally overrides
`domain`/`port` the same way they'd need to for testing an invite link
end-to-end today.

## `src/assistant/api/routes/users.py`

```python
@router.patch("/{uid}", response_model=UserResponse)
def update_user_endpoint(
    uid: uuid.UUID,
    body: UserUpdate,
    session: SessionDep,
    user: CurrentUser,
) -> UserResponse:
    if uid != user.uid:
        raise HTTPException(status_code=403, detail="Cannot update another user's profile")
    updated = update_user(
        session, uid, email=body.email, firstname=body.firstname, lastname=body.lastname,
    )
    return UserResponse.model_validate(updated)
```

The identity check happens *before* any DB lookup for a mismatched
`uid`, so a caller probing someone else's UID gets 403 regardless of
whether that UID exists — no existence leak, same information-hiding
instinct as `InviteNotUsableError`'s one generic response for every
invalid-invite reason. This also means the "PATCH an unknown uid" 404
case tested today no longer applies once auth is required (see Test
plan) — attempting to touch a UID that both differs from your own *and*
happens not to exist is indistinguishable, from the caller's side, from
attempting to touch someone else's real account, so it's 403 either way,
not 404.

`create_user_endpoint` (`POST /user`) and `get_user_endpoint`/
`list_users_endpoint` are unchanged — see "Further notes".

## Frontend

`frontend/src/api/client.ts` — export the base-URL join so a plain
`<a href>` (not a `fetch()`) can be built for the two endpoints the
frontend never calls via XHR:

```ts
export function apiUrl(path: string): string {
  return `${BASE_URL}${path}`;
}
```

`frontend/src/components/GoogleAuthButton.tsx` (new):

```tsx
interface GoogleAuthButtonProps {
  inviteId?: string;
}

export default function GoogleAuthButton({ inviteId }: GoogleAuthButtonProps) {
  const path = inviteId
    ? `/auth/google?invite_id=${encodeURIComponent(inviteId)}`
    : '/auth/google';
  return (
    <a href={apiUrl(path)} className="btn-google">
      Continue with Google
    </a>
  );
}
```

Plain link, not a click handler — this has to be a real top-level
navigation (per the "backend owns both ends" decision), not something
`apiFetch`'s `credentials: 'include'` machinery is involved in at all.

`frontend/src/lib/googleAuthErrors.ts` (new):

```ts
const GOOGLE_AUTH_ERROR_MESSAGES: Record<string, string> = {
  denied: 'Google sign-in was cancelled.',
  invalid_request: 'Something went wrong starting Google sign-in. Please try again.',
  invalid_state: 'Your Google sign-in session expired. Please try again.',
  google_failed: 'Google sign-in failed. Please try again.',
  unverified_email:
    "Your Google account's email isn't verified. Verify it with Google, or use a different sign-in method.",
  collision:
    'This email already has a password account. Log in with your password instead.',
  invite_email_mismatch:
    "You signed in with a different Google account than the one this invite was sent to.",
  registration_closed: 'This invite is no longer valid, or registration is currently closed.',
};

export function googleAuthErrorMessage(code: string | null): string | null {
  if (!code) return null;
  return GOOGLE_AUTH_ERROR_MESSAGES[code] ?? 'Google sign-in failed. Please try again.';
}
```

`frontend/src/components/RegistrationForm.tsx` (edit) — add a divider +
`<GoogleAuthButton inviteId={inviteId} />` below the existing submit
button. `RegistrationForm` already receives `inviteId`, so this covers
both `RegisterPage` (no invite) and `AcceptInvitePage` (with invite)
without touching either page's own logic.

`frontend/src/pages/LoginPage.tsx` (edit) — render
`<GoogleAuthButton />` (no `inviteId`) below the password form; read
`google_error` via `useSearchParams()` (react-router) and, if present,
show `googleAuthErrorMessage(searchParams.get('google_error'))` the same
way the existing `error` state already renders (`<p className="auth-error">`).

`frontend/src/pages/AcceptInvitePage.tsx` (edit) — same `google_error`
read/render, shown above the (already-present, via `RegistrationForm`)
Google button, so a failed Google attempt on this page surfaces its
error without leaving `/invite/:inviteId`.

Both `LoginPage`'s and `RegisterPage`'s Google-button failures land on
`/login?google_error=...` (see the route code above — only an invite
attempt gets its own distinct failure path). A user who clicks
"Continue with Google" from `/register` and hits an error therefore
lands on `/login`, not back on `/register` — a minor UX rough edge
flagged in "Further notes", not fixed here (fixing it means encoding
"which page did I come from" into `state` alongside `invite_id`, for a
case that's cheap to notice and correct later if it bothers anyone).

## Test plan

Following `AGENTS.md`'s TDD convention — module-level functions,
`# --- Section ---` separators.

**`tests/google_auth/test_state.py`** (new) — `sign_state`/`verify_state`
round-trip preserves `nonce` and `invite_id` (including `None`);
`verify_state` raises `GoogleStateInvalidError` for a garbage string, a
token signed with a different secret, and an expired token
(`monkeypatch` a past `exp` or use `freezegun`-style time control if the
repo has a precedent — confirm during implementation, else construct an
already-expired token directly via `jwt.encode`).

**`tests/google_auth/test_oauth.py`** (new) — `redirect_uri` composes
`https://{domain}:{port}{redirect_path}` from config (both the default
path and an overridden `GOOGLE_REDIRECT_PATH`). `build_authorization_url`
includes all required params (`client_id`, a `redirect_uri` matching
what `redirect_uri()` returns, `response_type=code`, `scope` containing
all three of `openid`/`email`/`profile`, `state`, `nonce`,
`prompt=select_account`).
`exchange_code_for_tokens`: mock `requests.post` (via `monkeypatch` or
`responses`-style fixture, matching whatever `tests/email/test_service.py`
already uses for Mailgun — confirm during implementation) — success
returns the parsed JSON; non-2xx and `RequestException` both raise
`GoogleTokenExchangeError`. `verify_id_token`: mock
`google.oauth2.id_token.verify_oauth2_token` — a valid claims dict with
matching nonce returns `GoogleIdTokenClaims` with the right fields; a
`GoogleAuthError`/`ValueError` from the library raises
`GoogleTokenInvalidError`; a mismatched `nonce` claim raises
`GoogleTokenInvalidError` even when the library call itself succeeds;
missing `given_name`/`family_name` in the claims dict map to `None`, not
a `KeyError`.

**`tests/invites/test_service.py`** (extend) — new cases for
`create_gated_user` directly: creates a `User` with the given
fields and `default_quota_for_new_user`'s result; a valid invite
converts it (reusing the same assertions `on_user_created`'s existing
cases already make); `registration_enabled=False` with no `invite_id`
raises `RegistrationDisabledError` and creates no row;
`invite_quota_override` takes precedence over the config default when
given. These cases, plus the existing (unmodified)
`tests/api/test_auth.py` registration matrix and `tests/api/test_users.py`
`TestCreateUser` suite continuing to pass unchanged, are the regression
coverage for the `register_user`/`create_user` refactor — neither
function's own test file needs new cases, since their observable
behavior doesn't change.

**`tests/google_auth/test_service.py`** (new) — `db_session` fixture,
matching `tests/invites/test_service.py`'s style. A fabricated
`GoogleIdTokenClaims`, varying one field at a time:
`email_verified=False` → `GoogleEmailNotVerifiedError`, no `User`
created; first-time claims with `registration_enabled=True`,
no `invite_id` → creates `User` + `Credential(provider="google",
provider_subject=sub)`; a second call with the *same* `sub` returns the
same `User` (login path, no new `Credential`); an email that already has
a `provider="password"` credential → `GoogleAccountCollisionError`, no
new rows; `registration_enabled=False`, no `invite_id` →
`RegistrationDisabledError` (propagated, not caught); a valid invite
whose `invitee_email` matches → succeeds, invite converts (assert via
`on_user_created`'s effect, same assertions style as
`tests/invites/test_service.py`); mismatched invite email →
`InviteEmailMismatchError`; missing `given_name` → `User.firstname == ""`,
not an exception.

**`tests/api/test_auth.py`** (extend) — `monkeypatch` the four
`google_auth.oauth`/`google_auth.state` boundary functions (not
`requests` — the unit-level tests above already cover those) so these
are true API-integration tests of the routing/redirect/cookie logic:
`GET /auth/google` redirects (302) to a URL starting with
`https://accounts.google.com`; the `state` it embeds round-trips through
`verify_state` back to the `invite_id` passed as a query param.
`GET /auth/google/callback`: `error=access_denied` → 302 to
`/login?google_error=denied`; missing `code`/`state` → 302 to
`/login?google_error=invalid_request`; a `state` that doesn't verify →
`invalid_state`; the service raising each of
`GoogleEmailNotVerifiedError`/`GoogleAccountCollisionError`/
`InviteEmailMismatchError`/`RegistrationDisabledError` maps to its
documented `google_error` code, and — critically — an invite-flow
failure (state carrying an `invite_id`) redirects to `/invite/{id}`,
not `/login`; success sets `access_token`/`refresh_token` cookies
(`"access_token" in client.cookies`, matching
`test_register_auto_logs_in`'s existing assertion style) and redirects
to a URL ending `/notebooks`; a second callback with the same Google
`sub` (simulating a returning user) logs in without creating a second
`User` row.

**`tests/api/test_users.py`** (extend) — `TestUpdateUser`'s four
existing cases (`test_update_user_partial`, `test_update_user_no_changes`,
`test_update_user_duplicate_email`) gain
`headers=make_auth_headers(test_user.uid)`. `test_update_user_not_found`
is replaced by two cases: unauthenticated `PATCH` → 401; authenticated
as `test_user`, `PATCH` targeting a *different* (nonexistent) UUID → 403
(not 404 — per the route's information-hiding rationale above). New
case: authenticated as `test_user`, `PATCH` targeting a second, real
user's UID → 403, and that second user's row is verifiably unchanged.

**`tests/test_config.py`** (extend) — `get_google_config()` returns
`client_id`/`client_secret` when set via YAML, `redirect_path` defaults
to `/auth/google/callback` when absent from YAML; each individually
env-overridable (`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`/
`GOOGLE_REDIRECT_PATH`); raises `ValueError` naming `client_id`/
`client_secret` (not `redirect_path`, which never causes a raise) when
those are missing, matching `get_mailgun_config`'s existing test
coverage shape.

**Frontend** `GoogleAuthButton.test.tsx` (new): renders an `<a>` whose
`href` ends `/auth/google` with no `inviteId` prop, and
`/auth/google?invite_id=<id>` with one. `RegistrationForm.test.tsx`
(new — didn't exist before this plan): renders the Google button
alongside the password form; the button's href reflects the `inviteId`
prop the same way the (already-tested) email-lock behavior does.
`LoginPage.test.tsx` (extend): renders the Google button; a
`?google_error=collision` URL renders the mapped message.
`AcceptInvitePage.test.tsx` (extend): a `?google_error=invite_email_mismatch`
URL renders the mapped message alongside the (valid-invite) form.

## Build order

1. `pyproject.toml` (`google-auth`) + `make sync`.
2. Config (`config.py`: `GoogleConfig` + `get_google_config`;
   `config.yaml` addition). TDD against extended `tests/test_config.py`
   first.
3. `auth/service.py`: rename `_jwt_secret` → `jwt_secret`. Sanity-check
   `make test` — purely a rename, expect zero behavior change.
4. `invites/service.py`: add `create_gated_user`, TDD against the new
   cases in `tests/invites/test_service.py`. Then refactor
   `auth/service.py::register_user` and
   `notes/user_service.py::create_user` to call it — `make test` on
   `tests/api/test_auth.py`'s registration matrix and
   `tests/api/test_users.py`'s `TestCreateUser` should pass unmodified;
   any failure here means the refactor changed behavior, not that a
   test needs updating. Depends on 2 (uses `get_registration_config`,
   unchanged, but keep the ordering explicit).
5. `google_auth/exceptions.py`, then `google_auth/state.py` (TDD against
   `tests/google_auth/test_state.py`). Depends on 3.
6. `google_auth/oauth.py` (TDD against `tests/google_auth/test_oauth.py`,
   all Google-network calls mocked). Depends on 2.
7. `google_auth/service.py` (TDD against `tests/google_auth/test_service.py`).
   Depends on 4 (`create_gated_user`) and 5-6 only for imports of their
   types; the tests themselves exercise this module directly with
   fabricated claims, no HTTP mocking needed here.
8. `api/routes/auth.py` (two new routes) — TDD against the extended
   `tests/api/test_auth.py`. Depends on 5-7.
9. `api/routes/users.py` (`PATCH` hardening) — TDD against the extended
   `tests/api/test_users.py`. Independent of 1-8, can be done any time
   (do it early to avoid the rest of the plan being blocked on a
   last-minute test rewrite).
10. `docs/architecture/authentication.md` rewrite. Depends on 1-9 being
    settled (so the doc describes what was actually built, not the plan).
11. Frontend: `api/client.ts` (`apiUrl`), `lib/googleAuthErrors.ts`,
    `components/GoogleAuthButton.tsx`, `RegistrationForm.tsx` edit,
    `LoginPage.tsx` edit, `AcceptInvitePage.tsx` edit. Depends on 8 (needs
    the real `google_error` codes and route shapes). TDD against the
    new/extended `*.test.tsx` files.
12. `make check` (backend) + `make frontend-check` + `make frontend-test`
    across everything touched.

## Verification

- `make check` passes (mypy strict, ruff, full pytest suite). Confirm
  `google-auth` ships type stubs / `py.typed` cleanly under this
  project's strict mypy config during step 5 — add a
  `[[tool.mypy.overrides]]` block (matching the existing `yaml`/
  `uvicorn` ignore-missing-imports entries) if it doesn't.
- `make frontend-check && make frontend-test` pass.
- Manual smoke test (requires a real Google OAuth client the user has
  set up, with its authorized redirect URI matching this app's composed
  `https://{domain}:{port}{google.redirect_path}` exactly, and
  `domain`/`port` set so the post-login redirect actually lands on a
  running frontend):
  - Fresh Google identity, open registration, no invite → click
    "Continue with Google" on `/login`, complete consent, land logged
    into `/notebooks`; confirm a `Credential(provider="google")` row
    exists and no password credential does.
  - Same Google account, log out, click "Continue with Google" again →
    logged back in as the same user, no duplicate `User` row.
  - A password-registered email, then attempt Google sign-in with a
    Google account sharing that email → redirected to
    `/login?google_error=collision`, message renders, no new rows.
  - `registration.registration_enabled: false` in `config.yaml`, restart
    the API, attempt Google sign-in as a brand-new identity with no
    invite → `/login?google_error=registration_closed`.
  - Create an invite via the existing invites flow, open
    `/invite/:id`, click "Continue with Google" using an account whose
    email matches the invite → registers and logs in, invite shows
    `converted`.
  - Same invite link, but authenticate with a *different* Google
    account → redirected back to `/invite/:id?google_error=invite_email_mismatch`,
    invite still `pending`.
  - `PATCH /user/{own-uid}` with a valid access token → 200; the same
    call with no auth → 401; with a *different* user's valid token,
    targeting your own uid → 403.

## Out of scope

- Bearer/native-app Google sign-in — cookie/web mode only, per the
  session's decision.
- Any account-linking / "switch auth mechanism" feature — a Google
  identity colliding with an existing password account is rejected
  outright, not offered a linking path.
- Rewriting `docs/architecture/authentication.md`'s "Provider Linking"
  section into a *new* design for a future linking feature — this plan
  only removes the stale, never-built auto-linking description; a real
  linking design is separate future work.
- Any UI for editing `firstname`/`lastname` after account creation
  (the `PATCH /user/{uid}` capability exists, hardened by this plan, but
  nothing in the frontend calls it for this purpose) — explicitly
  deferred per the session.
- Any email-confirmation flow for password signups — doesn't exist
  today, not built here; Google's `email_verified` claim is checked
  in-line, never persisted, so there's nothing here for a future
  confirmation feature to key off of.
- Fixing `POST /user`'s missing authentication — see "Further notes".
- Rate-limiting `/auth/google`/`/auth/google/callback`.
- Any change to `GET /user` / `GET /user/{uid}` (still unauthenticated,
  unchanged).

## Further notes

- **`POST /user` is intentionally left unauthenticated.** It already
  reuses `resolve_registration_gate` (`notes/user_service.py:41`), so —
  contrary to the framing during grilling — it does *not* bypass
  invite/registration-enabled gating; the "vulnerability" there was
  overstated. What's real: `POST /user` never sets a `Credential`
  (`create_user` takes no password), so a user minted this way starts
  with zero credentials and can't log in through any path that exists
  today. The residual risk is narrower still — email-squatting: while
  `registration_enabled=true`, anyone can `POST /user` with someone
  else's real email, permanently blocking that person's later
  legitimate registration (unique-email constraint). Locking this
  endpoint behind auth would break its own recently-built, deliberate
  use as an unauthenticated CLI-bootstrap path
  (`docs/plans/support_invites.md`'s "Further notes" / the `api_client.py`
  `create-user` command explicitly relies on it being "already-public").
  Properly fixing the squatting risk needs an actual bootstrap/admin-auth
  story this codebase doesn't have yet — bigger than this feature, and
  not required for Google SSO to be safe, so it's called out here rather
  than silently fixed or silently left unmentioned.
- `google_auth` importing `jwt_secret` from `assistant.auth.service` is
  a new `google_auth -> auth` edge; `auth` doesn't import from
  `google_auth`, so no cycle. `google_auth` also imports
  `create_gated_user` from `assistant.invites` — same edge
  `auth.service` and `notes.user_service` already have to `invites`,
  nothing new in kind; after this plan, `create_gated_user` (not
  `resolve_registration_gate` directly) is the one thing all three
  "mint a User" callers share.
- The `state` param doubles as this flow's only CSRF defense (an
  attacker can't forge a signed `state` without the server's secret) and
  its only session for round-trip data — there's deliberately no second,
  separate CSRF mechanism, since `state` already serves that purpose per
  the OAuth2 spec.
- `Credential.provider_subject` is `String(255)` — Google's `sub` claims
  are documented as being at most 255 ASCII characters, so no column
  widening needed.
