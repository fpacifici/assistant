# Attachments support

Users can attach files of any format to notes. The attachment appears as a
markdown link at the end of the note and can be downloaded via the API.

## Data model

```
Note 1─────────────────────────────┐
     │                             │
     │ 0..*                        │ 0..*
     ▼                             ▼
   File                          Node (type=attachment)
     │                             │
     │ 0..*                        │ 1
     ▼                             │
   Chunk                           └──► File (attachment_id FK)
```

**File** — metadata for a single upload:

| column              | type     | notes                              |
|---------------------|----------|------------------------------------|
| id                  | UUID PK  |                                    |
| note_id             | UUID FK  | → notes; cascade delete            |
| file_name           | string   | original file name                 |
| creation_timestamp  | datetime | used for TTL expiry                |
| state               | string   | `pending→uploading→complete/expired` |

**Chunk** — one piece of a multi-part upload:

| column             | type     | notes                    |
|--------------------|----------|--------------------------|
| id                 | UUID PK  |                          |
| file_id            | UUID FK  | → files; cascade delete  |
| part_number        | integer  | 1-based                  |
| file_name          | string   | path on disk             |
| creation_timestamp | datetime |                          |

**Node** (attachment type) — links note content to a file:

- `node_type = 'attachment'`
- `attachment_id` FK → files
- `payload` = pre-formatted markdown link `[filename](/files/{id})`

## State machine

```
pending ──── upload_chunk ────► uploading ──── complete ────► complete
   │                                │
   └──── TTL elapsed (lazy) ────────┘
                                    ▼
                                 expired
```

TTL is 24 hours. Expiry is checked lazily on `upload_chunk` and `complete`
calls (not by a background job).

## Storage abstraction

`FileStorage` is a `Protocol` with these operations:

| method         | description                                          |
|----------------|------------------------------------------------------|
| `write_chunk`  | Persist raw bytes for one part; returns disk path    |
| `read_chunk`   | Read bytes from a chunk path                         |
| `merge_chunks` | Concatenate all parts into a single file             |
| `read_file`    | Return the complete file bytes                       |
| `delete_chunk` | Remove a single chunk file                           |
| `delete_file`  | Remove the whole file directory                      |

`LocalFileStorage` stores data under `{base_path}/{file_id}/`:
- chunks: `chunk_{part_number}`
- merged: `file`

The base path is configured via `config.yaml → file_storage_path` (default
`data/files`).

## Upload API

All endpoints require authentication (JWT cookie). Only the note's owner can
upload.

| method | path                          | description                  |
|--------|-------------------------------|------------------------------|
| POST   | `/files`                      | Create file record → 201     |
| PUT    | `/files/{id}/parts/{n}`       | Upload chunk (raw bytes)→ 204 |
| PATCH  | `/files/{id}`                 | Complete upload → 200        |
| GET    | `/files/{id}`                 | Download whole file → 200    |
| DELETE | `/files/{id}`                 | Delete file → 204            |

Error codes: 404 (not found / wrong owner), 409 (bad state transition), 410 (expired).

## Frontend upload flow

1. User clicks 📎 in the `MarkdownToolbar`
2. Browser file picker opens (hidden `<input type="file">`)
3. `handleFileSelected` runs:
   - `POST /files` to create the file record
   - `PUT /files/{id}/parts/{n}` for each 1 MB chunk
   - `PATCH /files/{id}` to complete
   - `POST /notebook/{nb}/note/{n}/node` with `{ file_id }` to create the attachment node
   - `onAttached()` callback invalidates the React Query `nodes` cache
4. Error state is shown inline in the toolbar

## Rendering and download

The attachment node stores `payload = "[filename](/files/{id})"`. The
`BlockNote` editor renders it as a clickable markdown link. Clicking downloads
the file via `GET /files/{id}` which returns the file with
`Content-Disposition: attachment`.

## Deletion cascade

- Deleting an **attachment node** calls `delete_file_record` (removes DB row +
  disk files).
- Deleting a **note** iterates its attachment nodes and cleans up each file
  before deleting the note.

## Database migration

Existing databases created before this feature was added have a stale
`nodes.attachment_id` FK (pointing to the removed `attachment_metadata` table)
and an outdated check constraint.  `init_database()` / `setup_database`
automatically migrates both constraints on startup — safe to re-run.
