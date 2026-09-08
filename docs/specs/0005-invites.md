## Support invites

Today there are two ways to create a user: the password registration page and
CLI user creation, both always open. We want a third way — a registered user
invites someone by email, the recipient gets a unique URL, and visiting it
lets them register. We also want the ability to run the system **invite
only** in prod: registration and invites are each independently toggleable,
so an operator can require every new account to come through an invite.

This spec supersedes no prior spec — it is a new, self-contained feature.

## Registration modes

Four ways to create a user:

- Password registration page (`POST /auth/register`, no `invite_id`)
- Invite acceptance (`POST /auth/register`, with a valid `invite_id`)
- CLI user creation (`create-user`)
- CLI invite creation (`manage-invites create`)

The two CLI paths can never be disabled. The two config flags below gate the
other two, independently:

| | `registration_enabled=false` | `registration_enabled=true` |
|---|---|---|
| `invites_enabled=false` | Fully closed — only CLI can create users. Existing pending invite links stop working. | Open registration, no invites. |
| `invites_enabled=true` | **Invite-only mode.** `/register` requires a valid `invite_id`; without one, both the page and the API reject the request. | Default — open registration, invites also available. |

Enforcement is server-side, not just UI: `POST /auth/register` itself checks
these flags and 403s, independent of what the frontend shows. A disabled
mode's UI (button, page, nav link) is simply not rendered — the frontend
reads the flags from a small public config endpoint.

`invites_enabled=false` is a full kill switch: it also stops any
already-issued pending invite from being redeemed, not just new ones from
being created.

## Invite lifecycle

An invite has: `id` (embedded in the URL), `invitee_email`, `inviter_id`
(always a real registered user — CLI-issued invites must be attributed to
one), `created_at`, `expires_at`, and `state` (`pending` / `void` /
`converted`; only `pending` can transition).

- **Expiry: 1 day.** Checked lazily — there is no background sweep. A
  `pending` row past its `expires_at` simply fails validation when someone
  tries to use it; the sender's invite list computes and displays "expired"
  from the timestamp without the row itself changing state.
- **The URL is never stored.** It's `frontend_base_url + "/invite/" + id`,
  built fresh from current config every time it's shown. "Regenerate"
  therefore makes no database change at all — it exists only to reflect a
  changed `frontend_base_url` (e.g. a test environment's domain/IP
  changing), and is byte-identical to the original URL otherwise.
- **Re-inviting an already-invited, still-pending email always creates a
  new invite** (new id, consumes quota again) rather than reusing the
  pending one — the recipient may have lost the original link.
- **When any account is created for an email, by any path** — self
  registration, invite acceptance, or CLI user creation — every other
  `pending` invite addressed to that email (from any sender) is voided and
  refunded (see Quota below). The one invite actually used to register (if
  any) becomes `converted` instead. This also closes the race where a
  `pending` invite's email becomes registered a different way before the
  recipient clicks it: the invite simply isn't `pending` anymore by the time
  they do.
- Visiting an invite URL that is `void`, `converted`, `expired`, or
  nonexistent all produce the same generic "this invite is no longer valid"
  response — the three terminal states are never distinguished, since doing
  so would leak whether an account already exists for that address.
- On acceptance, the registration page's email field is **pre-filled from
  the invite and read-only**; the backend still independently validates the
  submitted email matches the invite (defense in depth against a tampered
  request).
- Both self-registration and invite-registration **auto-login** the new
  user on success (issuing session cookies), matching what `/auth/login`
  already does — today's plain registration does not, which this closes.

## Quota

- Every user has an `invite_quota_remaining` count, seeded at creation from
  the config default (**5**) — uniformly, for all four creation paths.
  `create-user` gets an optional override flag for a non-default starting
  quota.
- Creating an invite decrements the sender's quota by 1 immediately.
  Voiding one refunds it — whether voided manually by the sender, by an
  admin, or automatically as a side effect of the cascade rule above.
  Converting one (a successful registration) never refunds.
- Admin-issued invites (CLI `create`) bypass quota entirely: no decrement,
  and correspondingly no refund if later voided.
- Admin `replenish` **adds** a delta to a user's current quota; it never
  sets an absolute value.

## Sender experience

- A dedicated `/invites` page: current quota, a compose form (email →
  new invite, disabled at zero quota), a table of pending invites, and a
  collapsible table of history (`converted`/`void`).
- Each row shows its URL (recomputed fresh on every load) and, for
  `pending` rows, a Void button.

## Recipient experience

- Visits the URL out of band, lands on a dedicated `/invite/:id` page
  (distinct from `/register`, not a query-param variant of it).
- If valid: registration form with email locked to the invite's address.
- If not valid (any terminal state or unknown id): generic "no longer
  valid" message.

## Admin CLI (`manage-invites`)

Runs with direct DB access, authorized purely by shell access to the
server — there is no in-app admin role anywhere in this system (RBAC's six
roles, per `docs/specs/0003_role_based_access_control.md`, are all
subject-scoped, not system-wide), matching the existing precedent of
`setup_database`/`reset_db`.

- `create --as <sender-email> --to <invitee-email>` — issues an invite
  attributed to an existing user, bypassing their quota.
- `void --id <invite-id>` — force-voids any invite regardless of sender,
  refunding quota only if the invite had consumed any.
- `replenish --email <user-email> --amount <n>` — adds `n` to that user's
  quota.
- `delete --id <invite-id>` — permanently removes an invite row (refunding
  quota first if it was still pending and had consumed any); distinct from
  `void`, which keeps the row as sender-visible history.

A separate `delete-user --email <user-email>` CLI permanently deletes a
user and everything owned by them (notebooks, notes, entitlements,
invites sent) — a general account-management capability, not specific to
invites, documented alongside this one because it interacts with quota and
sent invites.

## Architecture

- New `assistant.invites` module owns all invite business logic (creation,
  voiding, conversion, quota, expiry checks) — mirrors `assistant.auth`'s
  shape, not nested under `notes`.
- Invite CRUD lives in its own route file (`api/routes/invites.py`).
  Accepting an invite is not separate CRUD — it's `POST /auth/register`
  gaining an optional `invite_id` field, since it's one registration flow
  with an optional extra input, not two operations.
- Config: a dedicated `invites` section in `config.py`'s `AssistantConfig`
  TypedDict (`registration_enabled`, `invites_enabled`, `default_quota`,
  `expiry_days`, `frontend_base_url`).

## Out of scope

- Emailing the invite link — still delivered out of band by the sender.
- Any tie-in with the note/notebook-sharing entitlement system
  (`docs/specs/0003_role_based_access_control.md`) — unrelated feature.
- Bulk/scripted deletion (e.g. "delete all expired invites") — the admin
  CLI's `delete` operations act on one invite/user at a time, by id/email.
