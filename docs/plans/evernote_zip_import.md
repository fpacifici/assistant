# Implementation plan: Evernote zip import from the web UI

Lets a user upload a zip of an Evernote HTML export from the web UI and
import it into their account. This builds on the HTML importer from #38 and
the fidelity fixes from #55, and closes out-of-scope item 2 ("UI zip-file
upload import flow") in [`docs/specs/adapters.md`](../specs/adapters.md).

The zip holds one directory per notebook. Each `.html` file in a directory is
one note. That is the same layout `HTMLFileImportSource` already reads from
disk, so the zip handling is mostly plumbing around `run_import`: storing the
upload, extracting it safely, calling the importer and cleaning up. The
import semantics also change (step 1). Notes are tracked in a new table, so
a re-import refreshes notes the user has not edited and leaves edited notes
alone, listing them in a report.

## Idempotency audit of the current importer

The import is meant to be idempotent: running it again with the same zip
must not create duplicates, and must reach the same final state.
`test_second_run_without_override_creates_no_duplicates` covers the normal
path, and that path works: notes are matched by `(notebook_id,
external_id = sha256(title))`, a DB unique constraint
(`uq_note_notebook_external_id`) backs the match, and each note is committed
on its own.

I ran three probe tests against `main` (4d85bbb, deleted after running). Each
found a case where the importer is **not** idempotent or loses data without
reporting it:

| # | Scenario | Observed | Why |
|---|---|---|---|
| A | A DB write fails partway through a note (here, its 2nd node) | Note `A` is committed with 1 of its 2 nodes. A re-run reports it as `skipped_existing`, so it stays incomplete forever. | `run_import`'s `except` logs the error but never calls `session.rollback()`. The half-written note stays in the session, and the next note's `commit()` saves it. (#38's description says a rollback was added. It is not in the current code.) An `IntegrityError` would also leave the session unusable, so every later note in the run would fail. |
| B | Two notes in one notebook have the same title (e.g. `Untitled.html`, `Untitled (1).html`) | The 1st note is imported. The 2nd is counted as `notes_skipped_existing` and never imported. | The dedup key is the title alone. |
| C | User B imports a notebook named `Personal` that user A already owns | All of B's notes fail. Stats are all zeros. The error only appears in the server log. | `Notebook.name` is globally unique. `find_or_create_notebook` returns A's notebook, and `create_note` then raises a permission error for each note. |

Fixes: A gets a rollback. B stays title-based but is now reported (see
"Import semantics"). C skips the notebook and reports it.

## Decisions

1. **Dedup and re-import.** The title stays the dedup key
   (`external_id = sha256(title)`, scoped per notebook). A new
   `note_imports` table records every note the importer created, with its
   import time. When a note with that key already exists:
   - if it was imported and not modified since: **refresh** it with the
     content from the zip;
   - if it was imported and modified since: **keep** it unchanged, and list
     it in the import report.
2. **Notebook owned by someone else (C).** If the notebook exists and the
   importing user cannot create notes in it, skip the whole notebook and
   list it in the report. Making notebook names unique per owner needs a
   schema migration and is a separate piece of work.
3. **Synchronous import.** The import runs inside the HTTP request (a sync
   endpoint, so it runs in FastAPI's threadpool) while the UI shows a
   spinner.
4. **No override in the UI.** The CLI's `--override` stays as an escape
   hatch: it also refreshes notes that were modified.
5. **When to delete the zip.** Always delete the zip and the extracted
   files, in a `finally`, whether the import succeeds or fails.

## Design

### `note_imports` table

| column | type | notes |
|---|---|---|
| `note_id` | UUID PK | FK → `notes.id`, `ON DELETE CASCADE` |
| `imported_at` | timestamptz | the note's `update_timestamp` right after the import wrote it |
| `source_path` | string | path of the source file inside the zip, e.g. `Work/Meeting.html` (for the report) |

The model is `NoteImport` in `models/schema.py`, added with an Alembic
migration in `alembic/versions/`.

**What "modified" means.** Every user edit already sets
`note.update_timestamp`. `_touch_note` runs on title updates and on every
node add, insert, update, split, merge and delete. So a note counts as
modified when `note.update_timestamp > note_import.imported_at`. The
importer's own writes also touch the note. To keep them from counting as
edits, `imported_at` is copied from `note.update_timestamp` *after* the last
write, in the same transaction, rather than taken from a separate
`now()`.

**Writes are recorded in the same transaction.** Creating or refreshing a
note and writing its `note_imports` row happen in the same commit. A
rollback (fix A) undoes both together.

### Import semantics (`run_import`)

For each document, in `list_documents` order (sorted, so deterministic):

| Situation | Action | Report bucket |
|---|---|---|
| No note with this `(notebook, external_id)` | Create the note and its nodes, and insert a `note_imports` row | `created` |
| Exists, tracked, not modified, parsed blocks identical to the stored nodes | Nothing | `unchanged` |
| Exists, tracked, not modified, content differs | `replace_markdown_nodes`, then update `imported_at` | `refreshed` |
| Exists, tracked, modified since import | Nothing (with `override=True`: refresh) | `kept_modified` (reported with title, notebook, import date, last edit date) |
| Exists but has no `note_imports` row (imported by the CLI before this table existed) | Nothing (with `override=True`: refresh and start tracking) | `kept_untracked` |
| Same key already handled earlier **in this run** (duplicate title in one notebook, case B) | Nothing | `duplicate_title` (reported with the source path) |
| Web clip and `include_web_clips` off | Nothing | `skipped_web_clip` |
| Notebook owned by someone else and not writable (C) | Skip all of the notebook's notes | `notebooks_failed` |
| Any exception | `session.rollback()`, continue | `failed` (with the source path and the error) |

Some consequences:

- **Idempotent.** Running the same zip twice gives the same state. The 2nd
  run reports everything as `unchanged` (or `kept_*` / `duplicate_title`),
  with no writes and no timestamp changes, because identical content is not
  rewritten.
- **Notes from before tracking are left alone.** The migration does not
  backfill rows for them. We cannot tell whether they were edited, so
  refreshing them could overwrite edits. They show up as `kept_untracked`.
  `--override` on the CLI refreshes them once and starts tracking them.
- **Deleted notes are imported again.** If a user deletes an imported note,
  its `note_imports` row is deleted with it (cascade), and the next import
  creates the note again. This matches "import what's in the zip".
- **Duplicate titles keep the first note.** Only the 1st note with a given
  title in a notebook is imported, using sorted path order. The others are
  listed in the report so nothing is lost without a mention.

`ImportStats` becomes an `ImportReport` dataclass: a count for each bucket,
plus lists of `KeptNote(title, notebook, source_path, imported_at,
modified_at)`, `DuplicateNote(title, notebook, source_path)`,
`FailedNote(source_path, error)` and `FailedNotebook(name, reason)`. The CLI
logs the counts and lists.

### Storage layout

New config key `import_storage_path`, default `data/imports`, which can be
overridden with the `IMPORT_STORAGE_PATH` env var. It works like
`file_storage_path` (`Config.get_import_storage_path()`).

```
data/imports/<user_uid>/<import_id>.zip    # uploaded, not imported yet
data/imports/<user_uid>/<import_id>/        # extracted while the import runs
```

`import_id` is a server-generated UUID. Clients never send a path, so
path traversal through the API cannot happen. Putting files under the user's
uid means one user cannot run another user's upload.

### Service: `src/assistant/adapters/zip_import.py`

The API layer stays thin (see AGENTS.md conventions). All of the logic lives
here:

- `store_upload(stream: BinaryIO, owner: User, *, max_bytes: int) -> uuid.UUID`
  copies the upload to `<user_uid>/<import_id>.zip` in chunks. It aborts and
  deletes the partial file if the upload is larger than `max_bytes`, and
  rejects the file if it is not a valid zip (`zipfile.is_zipfile`).
- `import_zip(session, import_id, owner, *, include_web_clips) -> ImportReport`:
  1. Resolves the path and raises `ImportNotFoundError` if it is missing.
  2. Extracts the zip safely into `<import_id>/`:
     - rejects absolute paths and `..` entries (zip-slip) and symlinks;
     - limits the number of entries and the total uncompressed size, to
       guard against zip bombs;
     - skips `__MACOSX/` and dotfiles (macOS Finder adds them).
  3. Finds the notebook root. If the zip has exactly one top-level directory
     and that directory contains no `.html` files, it is a wrapper folder
     (Finder's "Compress folder" creates one), so use it as the root.
  4. Runs `run_import(session, HTMLFileImportSource(root, include_web_clips=...), owner)`.
  5. In `finally`, deletes both the zip and the extracted directory.

Zip entry names are decoded as UTF-8 when the zip's UTF-8 flag is set, and
as cp437 otherwise (that is how `zipfile` behaves). Notebook names with
non-ASCII characters need a test.

### API: `src/assistant/api/routes/imports.py`, mounted at `/imports`

| Method | Path | Body | Response |
|---|---|---|---|
| `POST` | `/imports` | `multipart/form-data`, field `file` (.zip) | `201 {import_id}`. `413` if too large. `400` if not a zip. |
| `POST` | `/imports/{import_id}/run` | `{include_web_clips: bool}` | `200 ImportReportResponse` (the counts and lists above). `404` if the id is unknown or belongs to another user. `400` if the zip is unsafe or malformed. |

Both endpoints need an authenticated user (`CurrentUserId`).
`python-multipart` is already a dependency. The maximum upload size is a
config key (`import_max_upload_bytes`, default 500 MB). The kept-note
entries include `note_id` and `notebook_id` so the UI can link to the
notes.

### Frontend

- `frontend/src/api/imports.ts`: `uploadImportZip(file, onProgress)` uses
  `XMLHttpRequest`, because `fetch` cannot report upload progress, and sends
  cookies with `withCredentials`. `runImport(importId, opts)` uses
  `apiFetch`.
- `frontend/src/components/ImportDialog.tsx`: a file picker (`accept=".zip"`),
  an "Include web clips" checkbox, and an Import button. It then shows an
  upload progress bar, then "Importing…", then the **import report**:
  - counts for created, refreshed, unchanged, skipped web clips and failed;
  - **"Not updated because you edited them"**: the `kept_modified` notes,
    each linking to the note, with the import date and the last edit date;
  - "Imported before tracking, not updated": `kept_untracked`;
  - "Duplicate titles, not imported": `duplicate_title` with source paths;
  - failed notes and failed notebooks, with the reasons.

  Empty sections are hidden. When the import finishes the dialog
  invalidates the notebooks TanStack Query.
- Entry point: an "Import from Evernote" action on the notebooks list page,
  in the desktop header and in the mobile overflow menu (`OverflowMenu`).

## Steps

Each step is one commit, and each must pass `make check` (and
`make frontend-check` / `make frontend-test` for frontend steps). Backend
steps are TDD: regression tests first.

1. **`note_imports` table.** Add the `NoteImport` model, the Alembic
   migration and the service helpers in `notes/service.py`:
   `record_note_import(session, note, source_path)` (sets `imported_at` from
   `note.update_timestamp` after a flush) and
   `get_note_import(session, note_id)`. Tests: the row is written, deleting
   the note deletes the row (cascade), and the migration upgrades and
   downgrades cleanly.
2. **New `run_import` semantics + failure handling.** Tests, one per row
   of the semantics table:
   - re-import of an unmodified note with new content → refreshed, and
     `imported_at` is updated;
   - re-import with identical content → unchanged, with no writes:
     `update_timestamp` and `imported_at` do not change;
   - modified after import (node edit, and separately a title edit) → kept
     and reported, content untouched; with `override=True` → refreshed;
   - an untracked note with a matching `external_id` → `kept_untracked`;
     `override=True` refreshes it and creates its tracking row;
   - two notes with the same title in one notebook → the 1st is imported,
     the 2nd is reported as `duplicate_title`, and a 2nd run gives the same
     result;
   - probe A: `add_markdown_node` fails on the 2nd node → no partial note
     and no tracking row are committed, and a re-run imports the complete
     note;
   - probe C: another user's notebook → in `notebooks_failed`, and the
     other notebooks still import;
   - importing the fixture tree twice leaves exactly the same set of
     (notebook, title, ordered node payloads), and the 2nd run is all
     `unchanged`.

   Then implement: replace `ImportStats` with `ImportReport`, add
   `session.rollback()` in the `except`, check the notebook's `CREATE_NOTES`
   permission before importing into it, add the content comparison
   (ordered `(node_type, payload)` vs the parsed blocks), and update the CLI
   output and tests (`--override` keeps its flag, with its new meaning).
3. **Config + zip service.** Add `import_storage_path` and
   `import_max_upload_bytes`, plus `zip_import.py` with tests for: a normal
   zip, a wrapper folder, `__MACOSX`, zip-slip, a symlink entry, the size and
   entry-count limits, a non-zip file, cleanup on success, cleanup when
   `run_import` raises, a non-ASCII notebook name, and importing the same zip
   twice (2nd run: all `unchanged`).
4. **API routes.** Add `routes/imports.py` and `schemas/imports.py` and
   register the router. Route tests: upload then run returns the report, 404
   for another user's `import_id`, 413 and 400 errors, the zip is gone
   afterwards, and an unauthenticated request gets 401.
5. **Frontend API client + dialog.** Add `imports.ts` and `ImportDialog.tsx`
   with vitest tests (mocked API): the happy path shows counts, a report
   with kept-modified notes shows that section with links, empty sections
   are hidden, an upload error is shown, and the button is disabled until a
   file is chosen.
6. **Wire into the UI.** Add the entry points on the notebooks page (desktop
   and mobile) and update the route/layout tests.
7. **Docs.** Update `docs/specs/adapters.md` (the zip flow, the new
   re-import semantics replacing "skip existing", the meaning of
   `--override`, and the `note_imports` table), `docs/architecture/api.md`
   (new endpoints), `docs/architecture/adapters.md` and
   `docs/architecture/notesservice.md` (the new table), and add the new
   config keys to `config.yaml`.
8. **Manual end-to-end check** (with `make services-up` and `make dev`):
   - upload the real export and open a few notes;
   - **open a note in the editor without changing it** and confirm it is
     not reported as modified on the next import. If the editor saves
     anything on open, that bumps `update_timestamp`. PR #55 left this
     check unticked;
   - edit one note, re-upload the same zip, and confirm the report lists
     only that note under "edited", with everything else `unchanged`;
   - confirm `data/imports/` is empty.

## Risks

- **Saves that change nothing.** If the frontend saves a node without a
  real change, the note counts as modified and stops getting refreshed. It
  is reported, so nothing is lost, but the report would contain false
  positives. Step 8 checks for this. If it happens, the fix belongs in the
  frontend reconcile, not in the importer.
- **Clock comparison.** `imported_at` is copied from the same column the
  edit check compares against, and both values come from the API server's
  `datetime.now(UTC)`. So the comparison only depends on that server's
  clock. Running more than one API server with clocks out of sync could
  give wrong results at the margins. That is acceptable for now.

## Out of scope

- Background or async import jobs and progress reporting during the import.
- Making notebook names unique per owner instead of globally.
- Deleting stale uploads that were never imported. They stay in
  `data/imports/<uid>/` until a later cleanup task deletes them.
- Images and attachments inside the export (still placeholders, as in the
  spec).
- Merging imported changes into an edited note. Edited notes are only
  reported.
