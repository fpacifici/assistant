# Implementation plan: Sentry integration

Adds Sentry error reporting, tracing, profiling, logs (backend) and session
replay (frontend), with frontend traces continuing into the backend. Decisions
were reached in a `/grill-me` session; the Sentry projects already exist.

## Decisions recap (from grilling)

- **Frontend DSN is a build-time Vite variable** (`VITE_SENTRY_DSN`), passed
  as a Docker `ARG` exactly like `VITE_API_BASE_URL`. A DSN is public by
  design, so baking it into the bundle is fine, and it lets `Sentry.init` run
  before React renders.
- **Backend DSN lives in config** (`sentry.dsn` / `SENTRY_DSN`), never
  committed — same convention as `mailgun.apikey`.
- **No DSN → no init**, on both sides. Local dev and tests run with Sentry
  off unless the variable is set.
- **Sample rates are configurable** on both sides; defaults are the values
  from the Sentry onboarding snippets. An unparseable frontend rate falls
  back to its default instead of breaking the app.
- **`environment` is tagged** on both sides, default `development`.
- **No `release`, no source maps** in this change — deferred to a follow-up
  (needs `@sentry/vite-plugin` + a build-time `SENTRY_AUTH_TOKEN` secret).
- **Backend is initialised in `create_app()`** (runs in the uvicorn worker,
  so it works with `--reload`), via a single `init_sentry()`. Only the API
  server is instrumented for now; CLIs can opt in later by calling the same
  function.
- **Backend spans come from the SDK's auto-integrations**: FastAPI/Starlette
  (one transaction per API call), SQLAlchemy (one span per query), `requests`
  (Mailgun, Google OAuth), LangChain/OpenAI. No hand-written spans.
  Known gap: the langgraph `PostgresSaver` uses psycopg3 directly and will
  not produce DB spans — irrelevant until the RAG path is exposed via the API.
- **Logs**: `enable_logs=True` forwards Python logging at INFO+, excluding
  `uvicorn.access` (it duplicates transactions).
- **Frontend uses `@sentry/react`** (not `@sentry/browser`) with
  `reactRouterV7BrowserTracingIntegration`, so transactions are named after
  route patterns (`/notebooks/:notebookId/notes/:noteId`) and we can tell
  real routes from the catch-all.
- **Distributed tracing**: every `apiFetch`/`fetch` becomes an `http.client`
  span carrying `sentry-trace` + `baggage`. `tracePropagationTargets` =
  same-origin (prod, behind nginx) + the `VITE_API_BASE_URL` origin (dev,
  `:5173` → `:8000`). CORS already allows all headers.
- **Unauthenticated + no valid route is not instrumented**: traces and
  replays are dropped when the only match is the catch-all `*` route and
  there is no logged-in user. **Errors are still sent.** Logged-in users
  hitting `*` are still traced (dead links are worth seeing). The backend
  applies the same rule: drop transactions with no matched route and no
  authenticated user.
- **Replay privacy**: keep defaults (`maskAllText`, `blockAllMedia`). Note
  content is never unmasked. Unmasking UI chrome is out of scope for now.
- **User context**: id + email set on the Sentry scope once authenticated
  (both sides); cleared on logout (frontend).
- **Error capture in React**: `Sentry.ErrorBoundary` in `RootProviders`, and
  `Sentry.reactErrorHandler()` wired into `createRoot` error hooks. No custom
  frontend spans for now.

## Backend

### Dependency

Add `sentry-sdk[fastapi]>=2.35` to `[project.dependencies]` in
`pyproject.toml` (a version that supports `enable_logs` and
`profile_lifecycle`), then `make sync`.

### Config — `src/assistant/config.py`

New TypedDict and getter, following the `GoogleConfig`/`get_google_config`
pattern:

```python
class SentryConfig(TypedDict):
    dsn: str | None
    environment: str
    traces_sample_rate: float
    profile_session_sample_rate: float
```

`Config.get_sentry_config() -> SentryConfig`:

- `sentry.dsn` → `SENTRY_DSN` (`_get_typed_value(..., str)`; empty string
  treated as `None`).
- `sentry.environment` → `SENTRY_ENVIRONMENT`, default `"development"`.
- `sentry.traces_sample_rate` → `SENTRY_TRACES_SAMPLE_RATE`, default `1.0`.
- `sentry.profile_session_sample_rate` →
  `SENTRY_PROFILE_SESSION_SAMPLE_RATE`, default `1.0`.
- Rates are coerced with `float(...)` (YAML may give an `int` like `1`) and
  validated to `[0.0, 1.0]`; out of range raises `ValueError` (backend config
  errors fail fast, consistent with the rest of `Config`).

Add `sentry: SentryConfig` to `AssistantConfig`.

`config.yaml` gets a commented section:

```yaml
# Sentry (dsn is always supplied via SENTRY_DSN env var; omit it to disable)
sentry:
  environment: development
  # traces_sample_rate: 1.0            # optional, this is the default
  # profile_session_sample_rate: 1.0   # optional, this is the default
```

### New module — `src/assistant/observability.py`

```python
def init_sentry(config: Config | None = None) -> bool:
    """Initialise the Sentry SDK from config. Returns False (no-op) without a DSN."""
```

- Reads `get_sentry_config()`. No DSN → log at INFO
  ("Sentry disabled: no DSN configured") and return `False`.
- Otherwise calls `sentry_sdk.init(...)` with the snippet's options, taking
  `dsn`, `environment`, `traces_sample_rate`,
  `profile_session_sample_rate` from config, plus:
  - `send_default_pii=True`, `enable_logs=True`,
    `profile_lifecycle="trace"`
  - `before_send_transaction=drop_unrouted_anonymous_transaction`
  - `LoggingIntegration(sentry_logs_level=logging.INFO)` and
    `ignore_logger("uvicorn.access")` (from
    `sentry_sdk.integrations.logging`).
- Returns `True`.

`drop_unrouted_anonymous_transaction(event, hint) -> Event | None` — a
module-level pure function so it can be unit-tested:

- With the FastAPI integration's default `transaction_style="url"`, a matched
  request's transaction is named after the route template and
  `transaction_info.source == "route"`; an unmatched one falls back to the
  raw URL (`source == "url"`).
- Drop (return `None`) when `transaction_info.source != "route"` **and**
  `event.get("user", {}).get("id")` is absent. Otherwise return the event.
- Verify the exact `source` values against the installed SDK during
  implementation and adjust the check; the test pins the behaviour.

### Wiring — `src/assistant/api/app.py`

Call `init_sentry()` as the first statement of `create_app()`. The SDK's
FastAPI/Starlette/SQLAlchemy integrations auto-enable on import detection, so
no middleware changes are needed. `init_sentry` is idempotent enough for our
purposes (a repeat `sentry_sdk.init` replaces the client), but tests never
set a DSN so it is a no-op there.

### User context — `src/assistant/api/dependencies.py`

- `get_current_user_id`: after a successful decode,
  `sentry_sdk.set_user({"id": str(user_id)})`.
- `get_current_user`: once the `User` row is loaded,
  `sentry_sdk.set_user({"id": str(user.id), "email": user.email})`.

The SDK scopes these per request (isolation scope), so no cleanup is needed.
Calls are no-ops when Sentry is not initialised.

## Frontend

### Dependency

`cd frontend && npm install @sentry/react`.

### Env typing — `frontend/vite-env.d.ts`

Declare `ImportMetaEnv` with `VITE_API_BASE_URL`, `VITE_SENTRY_DSN`,
`VITE_SENTRY_ENVIRONMENT`, `VITE_SENTRY_TRACES_SAMPLE_RATE`,
`VITE_SENTRY_REPLAYS_SESSION_SAMPLE_RATE`,
`VITE_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE` (all `string | undefined`).

### New module — `frontend/src/lib/sentry.ts`

Keeps all Sentry setup out of `main.tsx` and exposes small pure helpers for
tests:

- `parseSampleRate(raw: string | undefined, fallback: number): number` —
  `Number(raw)`, returns `fallback` if not finite or outside `[0, 1]`.
- `buildTracePropagationTargets(apiBaseUrl: string | undefined): (string | RegExp)[]`
  — same-origin requests are always propagated by the SDK; if `apiBaseUrl`
  is a non-empty absolute URL, add a RegExp anchored to its origin
  (escaped), e.g. `^http://localhost:8000(/|$)`.
- `isCatchAllRoute(pathname: string): boolean` — uses `matchRoutes(routes,
  pathname)` from `react-router`; true when there is no match or the deepest
  match's route has `path === '*'`.
- `shouldDropTransaction(event): boolean` — true when the transaction name
  is the catch-all (ends in `*`, as produced by the router integration) and
  `Sentry.getCurrentScope().getUser()` / `event.user` has no `id`.
- `initSentry(router)`:
  - returns early if `VITE_SENTRY_DSN` is empty/unset;
  - `Sentry.init({ dsn, environment (default 'development'),
    integrations: [Sentry.reactRouterV7BrowserTracingIntegration({ useEffect,
    useLocation, useNavigationType, createRoutesFromChildren, matchRoutes })],
    tracesSampleRate, tracePropagationTargets, replaysSessionSampleRate,
    replaysOnErrorSampleRate, beforeSendTransaction: e =>
    shouldDropTransaction(e) ? null : e })`;
  - replay: if `!isCatchAllRoute(window.location.pathname)`, call
    `Sentry.addIntegration(Sentry.replayIntegration())` immediately.
    Otherwise defer it to `enableReplay()` (below), which runs once the user
    is known. Unauthenticated users on `*` are hard-redirected to `/login`
    by `AuthProvider`, which reloads the page with a valid route, so their
    replay starts there.
- `enableReplay()` — adds `replayIntegration()` once (guarded by
  `Sentry.getReplay()` / a module flag).
- `setSentryUser(user | null)` — `Sentry.setUser(user ? { id, email } : null)`
  and, when a user is set, `enableReplay()`.

With `createBrowserRouter`, the data-router variant is used:
`Sentry.wrapCreateBrowserRouterV7(createBrowserRouter)` in `main.tsx`
together with `reactRouterV7BrowserTracingIntegration`. Confirm during
implementation which of the two wiring styles the installed `@sentry/react`
expects for data routers and use that one.

### Wiring — `frontend/src/main.tsx`

- Call `initSentry()` before `createBrowserRouter`.
- Create the router via
  `Sentry.wrapCreateBrowserRouterV7(createBrowserRouter)(routes)`.
- `createRoot(el, { onUncaughtError: Sentry.reactErrorHandler(),
  onCaughtError: Sentry.reactErrorHandler(), onRecoverableError:
  Sentry.reactErrorHandler() })`.

### Error boundary — `frontend/src/components/RouteLayouts.tsx`

Wrap `RootProviders`' `<Outlet />` in `<Sentry.ErrorBoundary fallback={…}>`
with a minimal "Something went wrong — reload" fallback. Also set the data
router's `errorElement` on the root route to report route loader/render
errors via `Sentry.captureException` (router-caught errors don't reach the
React error boundary).

### User context — `frontend/src/contexts/AuthContext.tsx`

- `useEffect(() => setSentryUser(user ?? null), [user])` inside
  `AuthProvider`.
- In `logout`, call `setSentryUser(null)` before redirecting.

Timing note: the pageload transaction ends after the idle timeout, which
runs past the `/auth/me` fetch (a child span), so the user is normally set
before `beforeSendTransaction` runs. A test covers the filter logic; verify
the real ordering manually in the browser.

### Build — `docker/frontend/Dockerfile`

Add `ARG`/`ENV` pairs (default empty) for `VITE_SENTRY_DSN`,
`VITE_SENTRY_ENVIRONMENT`, `VITE_SENTRY_TRACES_SAMPLE_RATE`,
`VITE_SENTRY_REPLAYS_SESSION_SAMPLE_RATE`,
`VITE_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE`, next to `VITE_API_BASE_URL`, with
a comment that they are baked in at build time.

## Tests

### Python (`tests/`, module-level functions)

- `tests/test_config.py` (extend): `get_sentry_config` defaults; YAML values;
  env overrides (`SENTRY_DSN`, rates as strings → float); empty DSN → `None`;
  rate out of range → `ValueError`.
- `tests/test_observability.py` (new):
  - `init_sentry` with no DSN returns `False` and does not call
    `sentry_sdk.init` (monkeypatch).
  - `init_sentry` with a DSN calls `sentry_sdk.init` with the configured
    dsn/environment/rates and the fixed options (assert kwargs).
  - `drop_unrouted_anonymous_transaction`: route + anonymous → kept;
    url-source + user → kept; url-source + anonymous → dropped.
- `tests/api/…` (extend, if cheap): with `sentry_sdk.set_user` patched, an
  authenticated request sets `{"id", "email"}`.

### Frontend (Vitest)

- `frontend/src/lib/sentry.test.ts`: `parseSampleRate` (valid, empty,
  garbage, out of range); `buildTracePropagationTargets` (empty base URL →
  no extra target; `http://localhost:8000` → matches
  `http://localhost:8000/notebook/1`, not `http://localhost:80001`);
  `isCatchAllRoute` (`/notebooks/1/notes` → false, `/login` → false,
  `/wp-admin` → true); `shouldDropTransaction` (catch-all + no user → true,
  catch-all + user → false, real route + no user → false).
- `initSentry` with no DSN does not call `Sentry.init` (mock
  `@sentry/react`).

## Docs

- `docs/architecture/observability.md` (new): what is instrumented, config
  variables on both sides, the unrouted-anonymous filter rule, replay
  privacy, known gaps (psycopg3 checkpointer, no source maps/release).
- Link it from `docs/architecture/README.md`.
- `docs/devenv.md`: how to enable Sentry locally (`SENTRY_DSN` in `.env`,
  `VITE_SENTRY_DSN` in `frontend/.env.local`).
- Update `docs/architecture/frontend.md` briefly (Sentry init in `main.tsx`,
  error boundary in `RootProviders`).

## Manual verification

1. `make services-up`; set `SENTRY_DSN`, `SENTRY_ENVIRONMENT=development`
   and `VITE_SENTRY_DSN`; `make dev`.
2. Log in, open a note, edit and save. In Sentry: a pageload/navigation
   transaction named by route pattern, with `http.client` spans that
   continue into a backend `http.server` transaction containing `db` spans.
3. Logged out, open `/wp-admin` → no transaction, no replay in Sentry.
   Logged in, open `/does-not-exist` → transaction is recorded.
4. `curl localhost:8000/nope` → no backend transaction.
5. Throw in a component (temporary) → error appears with user id/email and a
   replay.

## Checks

- `make check` (typecheck + lint + test)
- `make frontend-check` and `make frontend-test`

## Follow-ups (out of scope)

- Source maps + `release` via `@sentry/vite-plugin` and a build secret.
- Instrument CLIs (importers, embeddings, chat) with `init_sentry()`.
- Selective replay unmasking of UI chrome.
- psycopg3 spans for the langgraph checkpointer when RAG is exposed via API.
