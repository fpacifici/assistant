# The API

As described in [`Architecture`](../README.md), we have two APIs systems:

- A rest API implemented with FastAPI
- A websocket API to manage the push based interactions.

All functionalities are supported with both APIs

## Rest API

The API is an OpenAPI implemented with FastAPI. It follows the REST principles.

### Authentication

We support two modes for authentication:

- JWT Token + refresh token passed as Httponly cookies. This is for interactions
  with the web UI

- Oauth2 style access token + refresh token for direct API access and mobile apps.

We will support two authentication mechanisms:

- user name and password. Identities are stored in the DB

- Google OAuth2 authentication

All tokens are stored in the DB for now.

**Current state**: Authentication is not yet implemented. The API uses an
`X-User-Id` header to identify the acting user. Endpoints that need to
know the current user (creating notebooks, listing notebooks, creating
notes) require this header. It will be replaced by JWT-based auth.

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

Create a notebook. Requires `X-User-Id` header.

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
    "owner_id": "uuid"
}
```

`GET /notebook`

List notebooks for the current user. Requires `X-User-Id` header.
Supports pagination via query parameters:
- `offset` (default: 0)
- `limit` (default: 20, max: 100)

`GET /notebook/{id}`

Retrieve a single notebook by UUID. Returns 404 if not found.

`PATCH /notebook/{id}`

Update a notebook. Currently only `name` can be updated.

Request body:
```json
{
    "name": "New Name"
}
```

`DELETE /notebook/{id}`

Delete a notebook and all its notes (cascade). Returns 204 on success,
404 if not found.

### Notes

`POST /notebook/{notebook_id}/note`

Create a note in a notebook. Requires `X-User-Id` header.
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
    "update_timestamp": "2026-01-01T00:00:00Z"
}
```

`GET /notebook/{notebook_id}/note`

List notes in a notebook. Supports pagination via `offset` and `limit`
query parameters.

`GET /notebook/{notebook_id}/note/{note_id}`

Retrieve a single note. The note must belong to the specified notebook,
otherwise returns 404.

`PATCH /notebook/{notebook_id}/note/{note_id}`

Update a note. Currently only `title` can be updated. The note must
belong to the specified notebook.

Request body:
```json
{
    "title": "Updated Title"
}
```

`DELETE /notebook/{notebook_id}/note/{note_id}`

Delete a note and all its nodes (cascade). The note must belong to
the specified notebook. Returns 204 on success, 404 if not found.

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

Requires `X-User-Id` header.

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

### Error Responses

All error responses follow the format:
```json
{
    "detail": "Error message"
}
```

Status codes:
- 404: Resource not found
- 409: Conflict (duplicate email, version conflict)
- 422: Validation error (missing/invalid fields or headers)

## Websocket

TBD
