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

The resource is `/notebook/.../note/.../node`
We support the following operations:

Add node with POST:
```
{
    position: .... # This is the position of the previous node
    payload: ....
}
```

We pick the position of the previous node and insert the node between that
position and the next at midpoint

PATCH `/notebook/.../note/.../node/...`
Splits a node
{
    offset: ... # The character at which to split
}

PUT `/notebook/.../note/.../node/...`
Two options:
Replace payload
{
    payload: ....
}

Merge nodes. The nodes have to be consecutive.
{
    nodes: [
        node1,
        node2,...
    ]
}

DELETE `/notebook/.../note/.../node/...`
Deletes a node.

**Current state**: Node endpoints are not yet implemented. The service
layer supports all node operations (add, insert, update, split, merge,
delete) and will be exposed in a future iteration.

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
