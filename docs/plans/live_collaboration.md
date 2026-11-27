# Implementation plan: live collaboration on notes

When two people have the same note open, each sees the other's edits, where
the other's cursor is, and that the other is there. The note list shows who
is on each note.

## Decisions

- **Polling, the reading list's mechanism.** The reading list does not push:
  `LinkList` polls with `refetchInterval`. Notes do the same. There is no
  websocket or SSE channel. The open note polls a *live* endpoint every
  `LIVE_POLL_MS` (2 s) while the page is visible. The note list polls
  presence every `NOTEBOOK_PRESENCE_POLL_MS` (10 s).
- **Heartbeat every 10 s.** While a note is open and the page is visible, the
  client sends a heartbeat every `HEARTBEAT_MS` (10 s). The heartbeat carries
  the cursor. A cursor move sends one too, throttled to 1 per second. Leaving
  the note (unmount, `pagehide`) deletes the presence with a `keepalive`
  request. A presence that has not beaten for `PRESENCE_TTL` (30 s, 3 missed
  beats) is no longer active.
- **Presence is per browser tab.** Each mounted editor makes a random
  `client_id`. Two tabs of the same user are two presences, and closing one
  does not hide the other. Lists show each user once, and never the caller.
- **Presence lives in Postgres.** One row per `(note, client)` in
  `note_presence`. The API is a single process today, but a table survives a
  restart, works with several workers, and is testable with the SQLite test
  database. Writes are about 1 per second per active user. Stale rows are
  deleted when any heartbeat is written.
- **Conflicts: first writer wins, per block**, as the server already does
  with node versions (optimistic locking, see
  [Notes service](../architecture/notesservice.md#concurrent-editing)).
  - Remote change to a block with no unsaved local edits: applied in place.
  - Remote change or delete of a block with unsaved local edits: the block is
    a *conflict*. It keeps the local text, is highlighted, is left out of
    saves, and offers **Keep mine** (re-apply the local text on top of the
    new version) or **Use theirs**.
  - A block deleted locally and not yet saved stays deleted: on the server a
    delete wins over an update, since `DELETE` carries no version.
  - A save answered 409 no longer stops autosave for the whole note. It
    polls right away, which turns that block into a conflict. The others keep
    saving.
- **Cursor: block and offset.** A cursor is `(node_id, offset)`: the server
  node of the block holding the caret, and the caret's character offset in
  it. A block that is not saved yet has no node, so no cursor is sent. The
  remote caret is drawn as a thin line with a round avatar holding the
  user's first initial, coloured from their user id.

## Backend

### Table `note_presence`

| Column | Type | |
| --- | --- | --- |
| `note_id` | UUID FK `notes.id`, `ON DELETE CASCADE` | PK part |
| `client_id` | UUID | PK part, made by the browser |
| `user_id` | UUID FK `users.uid`, `ON DELETE CASCADE` | |
| `cursor_node_id` | UUID, nullable, no FK | nodes come and go |
| `cursor_offset` | int, nullable | |
| `last_seen` | timestamptz | indexed |

Alembic migration after `e3b7c9d2a518`.

### Service `src/assistant/notes/presence.py`

- `heartbeat(session, note_id, caller, client_id, cursor)`: requires `view`
  on the note (`require_note_access`). Upserts the row with a portable
  select-then-update, since tests run on SQLite. A `client_id` already
  owned by another user is rejected. Deletes rows older than
  `PRESENCE_TTL` across all notes.
- `leave(session, note_id, caller, client_id)`: deletes the caller's row.
  Idempotent.
- `active_on_note(session, note_id, caller)`: the other users active on the
  note, one entry per user (their most recent cursor).
- `active_in_notebook(session, notebook_id, caller)`: for each note in the
  notebook that the caller can view, the other users active on it.
- `live_state(session, note_id, caller, since)`: the note's `revision`
  (`update_timestamp`, which `_touch_note` bumps on every change), its title,
  its nodes when `revision != since`, and `active_on_note`. Comparing for
  difference rather than order means a change can't be missed when commits
  land out of timestamp order.

### Routes (`src/assistant/api/routes/presence.py`, mounted under `/notebook`)

```
PUT    /notebook/{nb}/note/{note}/presence/{client_id}   body {cursor: {node_id, offset} | null}  -> 204
DELETE /notebook/{nb}/note/{note}/presence/{client_id}                                          -> 204
GET    /notebook/{nb}/note/{note}/live?since=<revision>                                         -> 200 LiveNote
GET    /notebook/{nb}/presence                                                                  -> 200 [NotePresence]
```

`LiveNote` is `{revision, title, nodes: NodeResponse[] | null, presence:
[ActiveUser]}`. `ActiveUser` is `{user_id, name, initial, cursor}`.
`NotePresence` is `{note_id, users: [ActiveUser]}`.

## Frontend

- `api/presence.ts`: `sendHeartbeat`, `leaveNote` (with `keepalive`),
  `fetchLiveNote`, `fetchNotebookPresence`.
- `markdown/liveMerge.ts`: a pure function that takes the server nodes, the
  editor document, the registry, the snapshot and the current conflicts. It
  returns the operations to apply: update a block, remove a block, insert
  after a block, or flag a conflict. It keeps the merge rules testable
  without the editor.
- `hooks/useNotePresence.ts`: the `client_id`, heartbeat timer, throttled
  cursor beats and leave on unmount or `pagehide`.
- `hooks/useLiveNote.ts`: polls `live` with React Query. It hands the nodes
  to the editor only when no save is in flight and no save started since the
  request was made, tracked with a save epoch. Otherwise a stale list could
  look like our newly created blocks were deleted.
- `NoteEditor`: applies merge operations while a `applyingRemote` ref
  suppresses `markDirty`, updates the snapshot for applied blocks, keeps
  conflicts in state, and `executeSave` skips conflicted blocks. A remote
  title shows when no title draft is pending.
- `components/RemoteCursors.tsx`: an overlay over the note body. It places
  each caret with `prosemirrorView.coordsAtPos` and falls back to the block's
  left edge.
- `components/PresenceAvatars.tsx`: the avatar stack, used in the editor
  toolbar and on each `NoteList` row.

## Tests

- Python (`tests/notes/test_presence.py`, `tests/api/test_presence.py`):
  heartbeat upsert, TTL, one entry per user, caller excluded, permissions
  (404 when the note is invisible), `client_id` owned by another user, leave
  idempotent, live returns nodes only when the revision changed, notebook
  presence filtered by visibility.
- Frontend: `liveMerge` rules (clean update, dirty update → conflict, remote
  delete clean and dirty, remote insert placement, local pending delete wins,
  stale versions ignored). Presence hook timers. Avatars on note rows. Editor
  applies a remote update and shows a conflict.

## Docs

Update `notesservice.md` (Concurrent editing: live updates and presence),
`api.md` (new routes), `frontend.md` (live collaboration section).
