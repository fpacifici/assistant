# The API

As described in [`Architecture`](../README.md), we have two APIs systems:

- A rest API implemented with FastAPI
- A websocket API to manage the push based interactions.

All functionalities are supported with both APIs

## Rest API

The API is an OpenAPI implemented with FastAPI. It follows the REST principles.

### Authentication

We support two modes for authentication, both JWT-based:

- A short-lived access token + a refresh token, passed as `Authorization:
  Bearer` headers. This is for direct API access.
- The same tokens, passed as `HttpOnly` cookies (`access_token`,
  `refresh_token`) instead. This is for the web UI.

A request may use the Bearer header or the cookie, never both at once — the
API rejects a request that supplies both with a 401. `POST /auth/login`
authenticates with email/password (identities stored in the DB, password
hashed) and returns both tokens; `POST /auth/refresh` rotates them.

Every endpoint below that needs to know the acting user (essentially all
notebook/note/node/sharing endpoints) resolves it from the access token —
there is no `X-User-Id` header or other unauthenticated identification.

Google OAuth2 authentication is planned but not yet implemented.

### User

`POST /user`

Create a user. Returns the created user with a generated UUID.

Request body:
```json
{
    "email": "user@example.com",
    "firstname": "Jane",
    "lastname": "Doe"
}
```

Response (201):
```json
{
    "uid": "uuid",
    "email": "user@example.com",
    "firstname": "Jane",
    "lastname": "Doe"
}
```

`GET /user`

List users. Supports pagination via query parameters:
- `offset` (default: 0)
- `limit` (default: 20, max: 100)

`GET /user/{uid}`

Retrieve a user by UUID. Returns 404 if not found.

`PATCH /user/{uid}`

Partial update of a user. All fields are optional.

Request body:
```json
{
    "email": "new@example.com",
    "firstname": "Updated"
}
```

### Notebooks

`POST /notebook`

Create a notebook. The caller becomes its owner (auto-granted the
`notebook_owner` role).

Request body:
```json
{
    "name": "My Notebook"
}
```

Response (201):
```json
{
    "id": "uuid",
    "name": "My Notebook",
    "owner_id": "uuid",
    "permissions": ["view_notebook", "update_notebook", "..."]
}
```

`permissions` is the caller's own effective permission set on this exact
object (see Sharing below) — every Notebook/Note response carries it, not
just this one.

`GET /notebook`

List notebooks visible to the current user: notebooks they have an
entitlement on directly, plus any notebook containing at least one note
they have an entitlement on (only that note is then visible when listing
its notes). Supports pagination via query parameters:
- `offset` (default: 0)
- `limit` (default: 20, max: 100)

`GET /notebook/{id}`

Retrieve a single notebook by UUID. Returns 404 if the caller cannot even
view it (whether or not it exists — visibility and existence are
indistinguishable to an unauthorized caller).

`PATCH /notebook/{id}`

Update a notebook. Currently only `name` can be updated. Requires the
`update_notebook` permission; 403 if the caller can view the notebook but
lacks it.

Request body:
```json
{
    "name": "New Name"
}
```

`DELETE /notebook/{id}`

Delete a notebook and all its notes (cascade). Requires `delete_notebook`.
Returns 204 on success, 404 if not visible, 403 if visible but lacking the
permission.

### Notes

`POST /notebook/{notebook_id}/note`

Create a note in a notebook. Requires the `create_notes` permission on the
notebook; the caller becomes the note's owner (auto-granted `note_owner`).
When creating a note we do not provide the nodes.

Request body:
```json
{
    "title": "My Note"
}
```

Response (201):
```json
{
    "id": "uuid",
    "notebook_id": "uuid",
    "owner_id": "uuid",
    "title": "My Note",
    "creation_timestamp": "2026-01-01T00:00:00Z",
    "update_timestamp": "2026-01-01T00:00:00Z",
    "permissions": ["view_note", "update", "delete_note", "share_note"]
}
```

`GET /notebook/{notebook_id}/note`

List notes visible to the caller in this notebook: all of them if the
caller holds `list_notes`/`view_notes`/`own_notes` on the notebook,
otherwise only the notes the caller has a direct entitlement on. Supports
pagination via `offset` and `limit` query parameters.

`GET /notebook/{notebook_id}/note/{note_id}`

Retrieve a single note. The note must belong to the specified notebook,
otherwise returns 404. Also 404 if the caller lacks `view_note`.

`PATCH /notebook/{notebook_id}/note/{note_id}`

Update a note. Currently only `title` can be updated. The note must
belong to the specified notebook. Requires `update`; 403 if visible but
lacking it.

Request body:
```json
{
    "title": "Updated Title"
}
```

`DELETE /notebook/{notebook_id}/note/{note_id}`

Delete a note and all its nodes (cascade). The note must belong to
the specified notebook. Allowed via `delete_note` on the note directly, or
`delete_notes`/`own_notes` on the parent notebook. Returns 204 on success,
404 if not visible, 403 if visible but lacking the permission.

### Nodes

The resource is `/notebook/{notebook_id}/note/{note_id}/node`.

Clients never see or send raw position strings — ordering is an internal
concern. When listing nodes (via GET on the note), the server returns them
in order. Clients reference nodes by ID when specifying insertion points.

Both merge nodes must belong to the same note (the one in the URL path).

#### List nodes

`GET /notebook/{notebook_id}/note/{note_id}/node`

List all nodes in a note, returned in position order.

Response (200):
```json
[
    {
        "id": "uuid",
        "note_id": "uuid",
        "author_id": "uuid",
        "node_type": "text",
        "payload": "Text content",
        "version": 1,
        "update_timestamp": "2026-01-01T00:00:00Z"
    }
]
```

#### Create node

`POST /notebook/{notebook_id}/note/{note_id}/node`

Requires `update` on the note (node mutations are note content edits).

Request body:
```json
{
    "payload": "Text content",
    "after_node_id": "uuid (optional)",
    "before_node_id": "uuid (optional)"
}
```

If neither `after_node_id` nor `before_node_id` is provided, the node is
appended at the end. If `after_node_id` is provided, the node is inserted
after that node. Both may be provided to insert between two specific nodes.

Response (201):
```json
{
    "id": "uuid",
    "note_id": "uuid",
    "author_id": "uuid",
    "node_type": "text",
    "payload": "Text content",
    "version": 1,
    "creation_timestamp": "2026-01-01T00:00:00Z",
    "update_timestamp": "2026-01-01T00:00:00Z"
}
```

#### Update node payload

`PATCH /notebook/{notebook_id}/note/{note_id}/node/{node_id}`

Uses a discriminated union body with `type: "update"`.

Request body:
```json
{
    "type": "update",
    "payload": "New text content",
    "expected_version": 1
}
```

Returns 409 if the version doesn't match (optimistic locking). The
response includes the current version so the client can retry.

Response (200): NodeResponse with bumped version.

#### Merge nodes

`PATCH /notebook/{notebook_id}/note/{note_id}/node/{node_id}`

The URL identifies the **target** node (the one that survives). The source
node is absorbed and deleted. Both must be text nodes in the same note.

Request body:
```json
{
    "type": "merge",
    "source_node_id": "uuid",
    "expected_version": 2,
    "source_expected_version": 1
}
```

`expected_version` is the target's version, `source_expected_version` is
the source's. Returns 409 if either version doesn't match.

Response (200): NodeResponse of the target with merged payload and bumped
version.

#### Split node

`POST /notebook/{notebook_id}/note/{note_id}/node/{node_id}/split`

Splits a text node at a character offset. The original node keeps
`payload[:offset]` and a new node is created with `payload[offset:]`
immediately after it.

Request body:
```json
{
    "offset": 12,
    "expected_version": 1
}
```

Returns 409 if the version doesn't match.

Response (201):
```json
{
    "original": { "id": "uuid", "payload": "left part", "version": 2, "..." : "..." },
    "new": { "id": "uuid", "payload": "right part", "version": 1, "..." : "..." }
}
```

#### Delete node

`DELETE /notebook/{notebook_id}/note/{note_id}/node/{node_id}`

Deletes a node. Idempotent — returns 204 whether or not the node existed.

### Sharing

Granting/revoking access — one pair of mirrored endpoint sets, nested under
notebooks and notes respectively. See
`docs/specs/0003_role_based_access_control.md` for the full role/permission
catalog and escalation rules.

```
POST   /notebook/{notebook_id}/share      body: {email, role}   -> Entitlement (201)
GET    /notebook/{notebook_id}/share                             -> list[Entitlement]
DELETE /notebook/{notebook_id}/share/{entitlement_id}            -> 204

POST   /notebook/{notebook_id}/note/{note_id}/share   body: {email, role}  -> Entitlement (201)
GET    /notebook/{notebook_id}/note/{note_id}/share                        -> list[Entitlement]
DELETE /notebook/{notebook_id}/note/{note_id}/share/{entitlement_id}       -> 204
```

`role` must be one of the three notebook roles (`notebook_owner`,
`notebook_viewer`, `notebook_editor`) for the notebook endpoints, or one of
the three note roles (`note_owner`, `note_viewer`, `note_editor`) for the
note endpoints — a role from the wrong subject type is a 422, not a 403.

Sharing/listing/revoking all require `share_notebook`/`share_note` on the
subject, and a grant or revoke can never exceed the caller's own current
effective permission level there (403 if it would). Sharing with an email
that has no account is a 404 — there is no pending-invite flow.

Entitlement response shape:
```json
{
    "id": "uuid",
    "principal_id": "uuid",
    "principal_email": "grantee@example.com",
    "role": "notebook_viewer",
    "created_at": "2026-01-01T00:00:00Z"
}
```

### Error Responses

All error responses follow the format:
```json
{
    "detail": "Error message"
}
```

Status codes:
- 401: Not authenticated (missing/invalid/ambiguous credentials)
- 403: Authenticated and can view the resource, but lacks the specific
  permission for the action (RBAC)
- 404: Resource not found, or the caller cannot even view it (a subject
  that exists but is invisible to the caller is indistinguishable from one
  that doesn't exist)
- 409: Conflict (duplicate email, version conflict)
- 422: Validation error (missing/invalid fields or headers)

## Websocket

TBD
