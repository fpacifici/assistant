# Adapters Layer

The adapters module imports external content directly into the notes system
(`Notebook`/`Note`/`Node`). There is a single flow today: importing an
Evernote HTML export.

> The original adapter layer (an `ExternalSource` plugin registry that synced
> Evernote into `documents` tables and a separate vector store) was removed;
> embeddings are built from the notes system itself, see
> [Vector search](./vectors.md). Notes imported through the web UI are
> embedded by the API server's worker; after a CLI import run
> `make reindex-vectors`.

## ImportSource

`ImportSource` (`adapters/import_source.py`) is the abstraction for one-shot
bulk imports. Fetching a document returns content already parsed into
storable blocks:

- `list_documents()` — returns identifiers for every document available to
  import (source-specific traversal, e.g. walking a directory tree).
- `get_note(document_id)` — fetches and parses one document, returning its
  target notebook name, title, and ordered blocks ready to persist as
  `MarkdownNode`s.

The only implementation is `HTMLFileImportSource`
(`adapters/plugins/html_file.py`), which treats a root directory's immediate
subdirectories as notebooks and each `.html` file inside as one note. HTML
is converted to markdown blocks by `adapters/html_parser.py`.

## Import pipeline

`run_import` (`adapters/notes_import.py`) drives an `ImportSource` and writes
through `notes/service.py`. It returns an `ImportReport`. It refreshes notes
it imported earlier only if nobody edited them since, tracked through the
`note_imports` table, and lists edited notes instead of overwriting them.

Two entry points use it:

- `zip_import.py` wraps the pipeline for the web UI: it stores an uploaded
  zip, extracts it safely and runs `HTMLFileImportSource` + `run_import` on
  it (see `POST /imports` in [the API](./api.md)).
- `python -m assistant.cli.import_html_notes` imports a local directory.

See `docs/specs/adapters.md` for the HTML adapter's detailed parsing and
import/re-import semantics.
