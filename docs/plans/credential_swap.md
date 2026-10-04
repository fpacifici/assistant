# Implementation plan: swapping a user's credential (password ⇄ Google)

## Goal

Each user still has exactly **one** authentication mechanism (no
multi-provider linking). What changes is that a user can *swap* it:

1. **Password → Google, from the login page.** Today a user with a
   password credential who clicks "Continue with Google" gets
   `?google_error=collision`. Instead, they are asked whether they want to
   switch their account to Google sign-in. On "yes" the password
   credential is deleted, a Google credential is created, and they are
   logged in. On "no" nothing changes.
2. **Google → password, from a new user settings page.** A logged-in
   Google user sets a password; the Google credential is deleted and the
   password credential replaces it.

## Context

- `Credential` (`src/assistant/models/schema.py`) already enforces
  `UNIQUE(user_id, provider)` and `UNIQUE(provider, provider_subject)`.
  "One mechanism per user" is a convention, not a DB constraint. **No
  schema migration needed.**
- The collision is raised in
  `google_auth.service.handle_google_callback`
  (`GoogleAccountCollisionError`) and mapped to
  `?google_error=collision` in `api/routes/auth.py:google_callback`.
- The callback is a top-level browser redirect and can't show a
  confirmation dialog. It has to save the verified Google identity
  somewhere, send the browser to a confirmation page, and finish the swap
  on a follow-up POST. The backend has no server-side session, so this
  plan reuses the signed-JWT approach already used for the OAuth `state`
  (`google_auth/state.py`).
- `docs/architecture/authentication.md` § "Provider collisions" says a
  switch mechanism is "future work". This plan is that work, and that
  section gets rewritten.

## Design decisions

- **Proof of ownership for password → Google.** Google has just verified
  the identity (`email_verified=true`, signed ID token, nonce checked),
  and its email equals the account email. That proves the person
  controls the account's email address, which is the same thing a
  password reset would prove. So the confirmation step asks only for
  consent, not the old password (the user forgot it in the common case).
  *Open question 1 below.*
- **The pending swap is carried in a short-lived signed cookie**, not in
  the URL. On collision the callback sets an `HttpOnly`, `SameSite=Lax`
  cookie `google_swap` (path `/auth/google/swap`, 10 min TTL) with a
  JWT `{purpose:"google_swap", user_id, sub, email, exp}` signed with
  `jwt_secret()`. Then it redirects to `/login/switch-to-google`. Keeping
  it out of the URL keeps it out of history, logs, and Referer headers.
  The `purpose` claim stops this token from being accepted as an OAuth
  `state` or an access token, and the other way round.
- **The swap happens in a single transaction:** delete the password
  credential, insert the Google credential, and delete all of the user's
  refresh tokens (this logs out any other sessions, since the old secret
  is gone). Then new tokens are issued for this browser.
- **PENDING users.** A password account that was never email-confirmed
  becomes `ACTIVE` on swap and its `EmailConfirmation` row is deleted,
  because Google has verified the email. This also gives unconfirmed
  users a way out.
- **Re-check at confirm time.** `POST` reloads the user and checks again
  that they still have a password credential, that the email still
  matches, and that no other user has claimed that Google `sub` since.
  The cookie is a hint, not an authority.
- **Invite path.** A collision during an invite flow goes to the same
  swap page. The invite is ignored because the account already exists.
- **Google → password needs an authenticated session** plus the new
  password typed twice (the frontend checks they match; the backend gets
  one value). Same min-length rule as registration. All refresh tokens
  are revoked and new ones issued. *Open question 2 below.*
- **Endpoints are generic about direction.** The settings page reads the
  current provider from `GET /auth/me`, which gains
  `auth_provider: "password" | "google"`. A future "switch back to
  Google" button in settings can reuse the existing `/auth/google`
  redirect, because the callback will route a logged-in collision
  through the same confirm page.

## Backend changes

### `src/assistant/auth/credentials.py` (new): swap service

New module in the service layer, per the AGENTS.md rule that routes don't
mutate ORM entities. It holds the only code that changes credentials
after a user exists.

```python
def get_auth_provider(session, user_id) -> Literal["password", "google"]
def swap_to_google(session, *, user_id, google_sub, email) -> User
def swap_to_password(session, *, user_id, password) -> User
```

- `swap_to_google`: loads the user and requires
  `user.email == email` and an existing password credential. Raises
  `GoogleAccountCollisionError` (reused) if the `sub` is already bound to
  another user. Deletes the password credential, adds the Google
  credential, activates a PENDING user and deletes its confirmation, and
  deletes all of the user's `RefreshToken` rows. Flushes.
- `swap_to_password`: requires a Google credential (raises
  `CredentialSwapError` if the user already uses a password). Deletes it,
  adds the argon2 password credential, revokes refresh tokens, flushes.
- Add `CredentialSwapError(AuthError)` to `auth/exceptions.py`.
- Move the password hashing (`_ph`) so `auth/service.py` and this module
  share one hasher. Expose `hash_password()` from `auth/service.py`.
- Add `revoke_all_refresh_tokens(session, user_id)` to `auth/service.py`.
  It is the bulk version of `logout_user`.

### `src/assistant/google_auth/swap_token.py` (new)

`sign_swap_token(user_id, sub, email) -> str` and
`verify_swap_token(raw) -> SwapClaims`. Same shape as `state.py`, plus a
`purpose` claim, and raises `GoogleStateInvalidError`-style
`GoogleSwapTokenInvalidError` (new, in `exceptions.py`).

### `src/assistant/google_auth/service.py`

`handle_google_callback` keeps raising `GoogleAccountCollisionError`, but
the exception now carries `user_id` and `sub` so the route can mint the
swap token without querying again. The service logic is otherwise
unchanged.

### `src/assistant/api/routes/auth.py`

- `google_callback`: on `GoogleAccountCollisionError`, set the
  `google_swap` cookie and redirect to `/login/switch-to-google` instead
  of `fail(..., "collision")`.
- `GET /auth/google/swap`: reads the cookie and returns `{email}` for the
  confirmation page. Returns 401 if the cookie is missing or invalid; the
  page then shows "session expired, try again".
- `POST /auth/google/swap`: reads the cookie, calls `swap_to_google`,
  commits, clears the `google_swap` cookie, sets the auth cookies, and
  returns `UserResponse`.
- `DELETE /auth/google/swap`: the "No, keep my password" button. Clears
  the cookie and returns 204.
- `POST /auth/credentials/password` (needs `CurrentUserId`): body
  `{password}`. Calls `swap_to_password`, commits, re-issues the auth
  cookies, and returns `UserResponse`. Returns 409 if the user is already
  a password user.
- `GET /auth/me`: `UserResponse` gains `auth_provider`, via
  `get_auth_provider`.

### `src/assistant/api/schemas/auth.py`

Add `auth_provider` to `UserResponse`. Add `GoogleSwapInfo{email}` and
`SetPasswordRequest{password}`, with the same password validation as
`RegisterRequest`.

## Frontend changes

- `api/auth.ts`: `getGoogleSwap()`, `confirmGoogleSwap()`,
  `cancelGoogleSwap()`, `switchToPassword(password)`. Add
  `auth_provider` to the `User` type.
- `pages/SwitchToGooglePage.tsx` (new, public route
  `/login/switch-to-google`). On mount it calls `getGoogleSwap()` and
  shows: "**{email}** already has a password account. Switch this
  account to Google sign-in? Your password will be removed and you'll
  sign in with Google from now on." It has two buttons:
  - **Switch to Google**: confirm, refresh the user context, and navigate
    to `/notebooks`.
  - **Keep my password**: cancel, then go to `/login` with the email
    pre-filled.
  If loading fails it shows the expired message and links back to
  `/login`.
- `pages/SettingsPage.tsx` (new, protected route `/settings`). It has a
  "Sign-in method" section showing the current provider.
  - For a Google user: a "Switch to password sign-in" form with new
    password and confirm fields and a warning that Google sign-in will be
    removed, then a `ConfirmDialog` before submitting.
  - For a password user: the text "You sign in with email and password."
    plus a "Switch to Google" button that goes to `/auth/google`. This
    works through the callback's collision → swap page with no extra
    backend work.
- `DesktopHeader.tsx` gets a "Settings" nav link next to "Invites". The
  mobile overflow menu gets the same entry.
- `routes.tsx`: register both routes.
- `lib/googleAuthErrors.ts`: remove the `collision` message, which can't
  happen any more. Keep a fallback.

## Tests

Backend (module-level functions, grouped by `# ---` separators):

- `tests/auth/test_credentials.py`:
  - swap to Google replaces the credential, activates a PENDING user,
    revokes refresh tokens, and rejects an email mismatch, a user
    without a password credential, and a `sub` already owned by someone
    else.
  - swap to password replaces the credential and rejects a user who
    already has a password.
- `tests/google_auth/test_swap_token.py`: round trip, expiry, and
  rejection of a token with the wrong `purpose` or an OAuth `state`
  token.
- `tests/api/test_auth.py`:
  - a callback collision sets the cookie and redirects to the swap page.
  - GET, POST, and DELETE swap, including a missing or expired cookie.
  - after a swap, password login fails and Google login succeeds.
  - `POST /auth/credentials/password` needs auth, swaps, returns 409 for
    a password user, and password login works afterwards.
  - `/auth/me` returns `auth_provider`.

Frontend (Vitest + RTL):

- `SwitchToGooglePage.test.tsx`: the confirm, cancel, and expired-cookie
  states.
- `SettingsPage.test.tsx`: rendering for each provider, password
  mismatch validation, and a successful switch.
- Update `LoginPage` and `googleAuthErrors` tests for the removed
  `collision` code.

## Docs

- `docs/architecture/authentication.md`: replace "Provider collisions"
  with a "Credential swap" section (flow diagram, swap cookie, what's
  revoked). Document the new endpoints and `auth_provider` on `/auth/me`.
- `docs/architecture/frontend.md`: the settings page and the swap page.

## Decisions after review

These override the parts of the plan above that say otherwise.
`docs/architecture/authentication.md` § "Credential swap" describes what
was built.

1. **Switching to Google asks for the current password.** The swap page
   has a password field and `POST /auth/google/swap` takes `{password}`.
   A wrong password returns 401 and keeps the pending switch usable.
   Users who forgot their password can't switch this way.
2. **Switching to password requires signing in with Google again.** An
   active session alone isn't enough. `POST /auth/google/reauth` returns
   a Google authorization URL whose signed `state` carries
   `reauth_user_id`. The callback checks that the returned Google
   identity belongs to that user, sets a 5-minute `google_reauth` cookie
   (scoped to `/auth/credentials`), and redirects to
   `/settings?reauth=ok`. `POST /auth/credentials/password` requires that
   cookie for the same user. Google's account chooser
   (`prompt=select_account`) is shown, but Google may not ask for the
   Google password again if its own session is still active.
3. **Switching to password doesn't require email confirmation.** Google
   already verified the email, so the account stays `ACTIVE`.
4. **The settings page only switches Google → password.** A "Switch to
   Google" button in settings would have let a logged-in user pick a
   Google account with a different email, which would sign them into, or
   create, a different account. Password users are told to sign out and
   use "Continue with Google" instead.
5. **A Google identity collision still fails.** If the email belongs to
   a user with a *different* Google identity (a different `sub`), the
   sign-in is still rejected with `?google_error=collision`.

## Out of scope

- Having both credentials at once (true account linking).
- Password reset / "forgot password" flow.
- Changing the password of an existing password user. The settings page
  could grow this later using the same `hash_password` helper.
