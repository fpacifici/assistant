# Observability (Sentry)

Both the API server and the web frontend report to Sentry: errors, tracing,
profiling and logs on the backend; errors, tracing and session replay on the
frontend. Frontend traces continue into the backend, so one trace covers a
click, the API call it made and the SQL queries that served it.

Sentry is **off unless a DSN is configured**, on both sides. Local dev and
tests run without it (the test suite forces `SENTRY_DSN=""`).

## Backend

`assistant.observability.init_sentry()` is the single entry point. It is
called as the first statement of `create_app()`, so it runs in the uvicorn
worker (works with `--reload`). Only the API server is instrumented; CLIs can
opt in by calling the same function.

Spans come from the SDK's auto-enabled integrations — there are no
hand-written spans:

| Integration | Produces |
|---|---|
| FastAPI / Starlette | one `http.server` transaction per request, named after the route template |
| SQLAlchemy | one `db` span per query |
| `requests` | `http.client` spans (Mailgun, Google OAuth) |
| LangChain / OpenAI | LLM spans |

Other options: `send_default_pii=True`, `profile_lifecycle="trace"`
(profiles follow sampled transactions), `enable_logs=True` with Python
logging forwarded at INFO+. `uvicorn.access` is excluded from both logs and
breadcrumbs because it duplicates the transactions.

The authenticated user (`id` = `User.uid`, `email`) is set on the
per-request scope by `get_current_user_id` / `get_current_user` in
`api/dependencies.py`.

### Configuration

| Config key | Env var | Default |
|---|---|---|
| `sentry.dsn` | `SENTRY_DSN` | unset → disabled. Never committed. |
| `sentry.environment` | `SENTRY_ENVIRONMENT` | `development` |
| `sentry.traces_sample_rate` | `SENTRY_TRACES_SAMPLE_RATE` | `1.0` |
| `sentry.profile_session_sample_rate` | `SENTRY_PROFILE_SESSION_SAMPLE_RATE` | `1.0` |

Rates outside `[0.0, 1.0]` make `Config.get_sentry_config()` raise at
startup.

## Frontend

`frontend/src/lib/sentry.ts` holds all setup; `main.tsx` calls
`initSentry(routes)` before creating the router with
`Sentry.wrapCreateBrowserRouter(createBrowserRouter)`, and uses
`Sentry.reactRouterBrowserTracingIntegration` so transactions are named after
route patterns (`/notebooks/:notebookId/notes/:noteId`).

- **Errors**: `Sentry.reactErrorHandler()` on the React root's error hooks,
  `Sentry.ErrorBoundary` in `RootProviders`, and the root route's
  `errorElement` for errors the data router catches itself.
- **Distributed tracing**: every `fetch` becomes an `http.client` span
  carrying `sentry-trace` + `baggage`. Same-origin requests (production,
  behind nginx) always propagate; the `VITE_API_BASE_URL` origin (dev,
  `:5173` → `:8000`) is added to `tracePropagationTargets`. CORS already
  allows all headers.
- **Replay**: default privacy — `maskAllText` and `blockAllMedia`. Note
  content is never unmasked.
- **User**: `AuthProvider` sets `{ id, email }` once `/auth/me` resolves and
  clears it on logout.

### Configuration

Vite variables, baked into the bundle at build time (Docker `ARG`s in
`docker/frontend/Dockerfile`). The DSN is public by design.

| Variable | Default |
|---|---|
| `VITE_SENTRY_DSN` | unset → disabled |
| `VITE_SENTRY_ENVIRONMENT` | `development` |
| `VITE_SENTRY_TRACES_SAMPLE_RATE` | `1.0` |
| `VITE_SENTRY_REPLAYS_SESSION_SAMPLE_RATE` | `0.1` |
| `VITE_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE` | `1.0` |

An unparseable or out-of-range rate falls back to its default rather than
breaking the app.

## Unrouted anonymous traffic is not instrumented

Scanners and typos should not cost trace or replay quota. On both sides,
**transactions** are dropped when the request matched no real route **and**
there is no authenticated user. **Errors are always sent.** Logged-in users
hitting a dead link are still traced.

- Backend: `drop_unrouted_anonymous_transaction` (`before_send_transaction`)
  drops events whose `transaction_info.source` is not `"route"` (the SDK
  uses `"url"` for unmatched requests) and that have no `user.id`.
- Frontend: `shouldDropTransaction` drops transactions whose name ends in `*`
  (the catch-all route, named `/*`) with no user. Replay is started
  immediately on a real route; on the catch-all it waits until a user is
  set. Anonymous visitors on protected routes (including `*`) are
  hard-redirected to `/login`, where replay starts on the fresh page load.

## Known gaps

- The langgraph `PostgresSaver` uses psycopg3 directly and produces no DB
  spans (irrelevant until the RAG path is exposed via the API).
- No `release` and no source maps yet: frontend stack traces are minified.
  Needs `@sentry/vite-plugin` and a build-time `SENTRY_AUTH_TOKEN`.
- CLIs (importers, embeddings, chat) are not instrumented.
