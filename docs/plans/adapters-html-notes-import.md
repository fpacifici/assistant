# Implementation plan: HTML notes directory import

Implements `docs/specs/adapters.md`.

## Context

`docs/specs/adapters.md` specifies a new import path that takes a directory tree of exported HTML notes and writes them into the real notes system (`Notebook`/`Note`/`Node`) as first-class, editable Notes — not into the existing RAG/`Document`/vector-store pipeline, which stays completely untouched. Today the only adapter (Evernote) only ever lands content in the RAG pipeline; there is no way to get external notes into the actual notes-taking product.

This plan implements that spec as a new **import** capability living in the `adapters` module (`docs/architecture/adapters.md` gets a short high-level appendix — see below): a pure HTML→blocks parser, an `ImportSource` abstraction (deliberately separate from `ExternalSource`, which is shaped for incremental RAG ingestion, not one-shot directory imports into Notes), a single `HTMLFileImportSource` implementation of it, an import pipeline that talks to the DB via `notes/service.py`, and a CLI entrypoint that authenticates as a real user before writing anything.

Two small schema changes are required (`Note.external_id` for dedup, a uniqueness constraint on `Notebook.name`), both additive and non-breaking for existing data.

None of this lives inside the `notes` package itself — `notes/` gains only genuine notes-domain persistence primitives (notebook/note/node CRUD helpers); parsing, directory traversal, and import orchestration are adapters-layer concerns and stay there, symmetric with how `notes/` has no knowledge of `ExternalSource`/RAG today.

## New/changed files

- `docs/architecture/adapters.md` — edit. Append a high-level "Notes Import" section describing the new `ImportSource` abstraction alongside the existing `ExternalSource` one. *(Already applied as part of this planning pass.)*
- `docs/specs/adapters.md` — edit. Update the block-mapping rule so skipped table/image nodes leave a placeholder paragraph instead of being fully dropped. *(Already applied as part of this planning pass.)*
- `src/assistant/adapters/html_parser.py` — new. Pure HTML→blocks parser, no DB/IO, no knowledge of files or directories.
- `src/assistant/adapters/import_source.py` — new. `ImportSource` ABC + `ImportedNote` dataclass.
- `src/assistant/adapters/plugins/html_file.py` — new. `HTMLFileImportSource(ImportSource)` — directory traversal + per-file fetch/parse.
- `src/assistant/adapters/notes_import.py` — new. `run_import`/`ImportStats` pipeline; drives an `ImportSource` and writes through `notes/service.py`. Mirrors `dataload.py`'s shape for the RAG path.
- `src/assistant/adapters/__init__.py` — edit. Export `ImportSource`, `HTMLFileImportSource`, `run_import`, `ImportStats`.
- `src/assistant/notes/service.py` — edit. Add `find_or_create_notebook`, `get_note_by_external_id`, `replace_markdown_nodes`; extend `create_note`; harden `create_notebook`.
- `src/assistant/notes/exceptions.py` — edit. Add `DuplicateNotebookNameError`.
- `src/assistant/models/schema.py` — edit. `Note.external_id` column + composite unique constraint; `Notebook.name` unique constraint.
- `src/assistant/models/database.py` — edit. Postgres migration helper for the two new constraints, called from `init_database()`.
- `src/assistant/cli/import_html_notes.py` — new. argparse CLI: auth precedence, `--override`, constructs `HTMLFileImportSource` and invokes `notes_import.run_import`.
- `pyproject.toml` — edit. Add `beautifulsoup4` to `[project.dependencies]`.
- `tests/adapters/test_html_parser.py`, `tests/adapters/test_html_file_import_source.py`, `tests/adapters/test_notes_import.py`, `tests/cli/test_import_html_notes.py` — new.
- `tests/adapters/fixtures/html_import/` — new fixture directory tree of real HTML files.

## Architecture doc change (applied)

Appended to `docs/architecture/adapters.md`:

> ## Notes Import
>
> Alongside `ExternalSource` (incremental sync into the RAG `Document`/vector-store
> pipeline), the adapters module also defines `ImportSource`: an abstraction for
> one-shot bulk imports of external content directly into the notes system
> (`Notebook`/`Note`/`Node`), bypassing `Document` and the vector store entirely.
>
> `ImportSource` mirrors `ExternalSource`'s two-method shape but is not
> incremental — there is no `since` cursor, and fetching a document returns
> content already parsed into storable blocks rather than raw bytes:
>
> - `list_documents()` — returns identifiers for every document available to
>   import (source-specific traversal, e.g. walking a directory tree).
> - `get_note(document_id)` — fetches and parses one document, returning its
>   target notebook name, title, and ordered blocks ready to persist as
>   `MarkdownNode`s.
>
> The only implementation today is `HTMLFileImportSource`, which treats a root
> directory's immediate subdirectories as notebooks and each `.html` file inside
> as one note. There is no `Registry`/DB-config layer for `ImportSource`
> instances yet — a single implementation is constructed directly by its CLI
> entrypoint. Import runs are orchestrated by a pipeline (`notes_import.py`,
> shaped like `dataload.py`) that drives an `ImportSource` and writes through
> `notes/service.py`.
>
> See `docs/specs/adapters.md` for the HTML adapter's detailed parsing and
> import/override semantics.

This keeps the ERD/`ExternalSource` sections above untouched — `ImportSource` is
a sibling abstraction, not a replacement.

## Spec change (applied)

In `docs/specs/adapters.md`, under **HTML directory adapter → Block mapping**,
the "tables and images are ignored... dropped cleanly" bullet is replaced with:

> - Tables and images are not rendered, but they are **not silently dropped**
>   either: each produces a single placeholder `paragraph` block stating what
>   kind of block was skipped (e.g. a table becomes a paragraph reading
>   `Skipped block: table`; an image becomes `Skipped block: image`), so the
>   note's structure and block count reflect the original content. Real
>   table/image rendering is tracked as an explicit TODO (see Out of Scope).
> - This placeholder treatment applies only to element types the parser
>   recognizes and deliberately does not render (currently: `table`, `img`).
>   It does **not** apply to inline `style`/`class` attributes, which continue
>   to be silently ignored throughout — a "skipped block" placeholder is about
>   skipped *content*, not skipped *styling*.

User story 9 is reworded to match ("...so that I get a clean note with a clear
marker where content was skipped, instead of corrupted or silently missing
content").

## Schema changes

In `src/assistant/models/schema.py`:

**`Note`** (currently `__table_args__ = {"schema": "assistant"}`, a bare dict — schema.py:200): convert to tuple form (matching `Node`'s existing pattern at schema.py:315-329) and add:
```python
external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
```
```python
__table_args__ = (
    UniqueConstraint("notebook_id", "external_id", name="uq_note_notebook_external_id"),
    {"schema": "assistant"},
)
```
Postgres/SQLite both treat multiple `NULL`s as non-colliding in a unique constraint, so regular in-app notes (`external_id IS NULL`) are unaffected.

**`Notebook`** (schema.py:171, same bare-dict pattern): convert to tuple form and add:
```python
__table_args__ = (
    UniqueConstraint("name", name="uq_notebook_name"),
    {"schema": "assistant"},
)
```
This is deliberately **global**, not per-owner — an explicit "for now" simplification from the spec (flagged there as a known multi-user limitation). `find_or_create_notebook` (below) resolves by name only, ignoring ownership of an existing match.

In `src/assistant/models/database.py`: `create_all()` won't retroactively alter an already-deployed Postgres schema. Follow the exact existing precedent of `_migrate_node_attachment_constraints` (database.py:143-204): add `_migrate_note_notebook_constraints(engine: Engine) -> None` that checks `information_schema`/`pg_constraint` for `uq_note_notebook_external_id` and `uq_notebook_name`, adding each via `ALTER TABLE ... ADD CONSTRAINT` if missing (no-op on a fresh DB where `create_all` already created them). Call it from `init_database()` right after `_migrate_node_attachment_constraints(engine)`, under the same `if engine.dialect.name == "postgresql":` guard (database.py:136-137). Note: on a pre-existing dev DB that already has two notebooks with the same name, the `uq_notebook_name` `ALTER TABLE` will fail loudly — expected and acceptable (dev-only DB, `make services-down && make services-up && python -m assistant.cli.setup_database` resets it if needed).

SQLite test fixture (`tests/conftest.py`) needs no migration logic — `create_all()` builds the constraints fresh every run.

## Service layer changes (`src/assistant/notes/service.py`)

These are the only `notes/` changes — plain persistence primitives with no awareness of HTML, files, or directories, consistent with constraint (1).

Add near the existing Notebook CRUD section (after `create_notebook`, service.py:101-109):
```python
def find_or_create_notebook(session: Session, name: str, owner_id: uuid.UUID) -> Notebook:
    """Return the existing Notebook named `name`, or create one owned by owner_id.

    Notebook.name is globally unique, so an existing match may belong to a
    different owner than owner_id — it is returned as-is, ownership is never
    reassigned. This matches the spec's "for now" global-uniqueness decision.
    """
    existing = session.scalar(select(Notebook).where(Notebook.name == name))
    if existing is not None:
        return existing
    return create_notebook(session, name, owner_id)
```

Harden `create_notebook` itself (service.py:101-109) so a direct name collision (outside the find-or-create path) fails with a clean domain exception instead of a raw `IntegrityError`, consistent with every other failure mode in this service:
```python
def create_notebook(session: Session, name: str, owner_id: uuid.UUID) -> Notebook:
    notebook = Notebook(name=name, owner_id=owner_id)
    session.add(notebook)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise DuplicateNotebookNameError(name) from None
    return notebook
```

Extend `create_note` (service.py:162-176) with a trailing keyword-only param, backward compatible:
```python
def create_note(
    session: Session,
    notebook_id: uuid.UUID,
    owner_id: uuid.UUID,
    title: str,
    *,
    external_id: str | None = None,
) -> Note:
    note = Note(
        notebook_id=notebook_id,
        owner_id=owner_id,
        title=title,
        external_id=external_id,
        update_timestamp=datetime.now(UTC),
    )
    session.add(note)
    session.flush()
    return note
```

Add near `get_ordered_nodes` (service.py:254-260):
```python
def get_note_by_external_id(session: Session, notebook_id: uuid.UUID, external_id: str) -> Note | None:
    """Look up a Note by its (notebook_id, external_id) dedup key. None if absent."""
    return session.scalar(
        select(Note).where(Note.notebook_id == notebook_id, Note.external_id == external_id),
    )
```

Add near the markdown-node section (service.py:381+), reusing `_validate_block_type`/position logic already there:
```python
def replace_markdown_nodes(
    session: Session,
    note_id: uuid.UUID,
    author_id: uuid.UUID,
    blocks: list[tuple[str, str]],  # (block_type, payload) pairs, in order
) -> list[Node]:
    """Delete all of a note's existing nodes and recreate them from `blocks`."""
    session.execute(delete(Node).where(Node.note_id == note_id))
    created = [
        add_markdown_node(session, note_id, author_id, payload, block_type)
        for block_type, payload in blocks
    ]
    _touch_note(session, note_id)
    session.flush()
    return created
```

`src/assistant/notes/exceptions.py`: add
```python
class DuplicateNotebookNameError(NotesServiceError):
    """Raised when creating a notebook whose name already exists."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"Notebook name already exists: {name}")
```

`replace_markdown_nodes` and `create_note` deal only in plain `(block_type, payload)` tuples / scalar args — they know nothing about `ParsedBlock` or any adapters-layer type. The pipeline (`notes_import.py`) is responsible for converting `ParsedBlock` objects into those tuples before calling into `notes/service.py`, keeping the dependency direction one-way (adapters → notes, never the reverse).

## Parser (`src/assistant/adapters/html_parser.py`)

Pure function, zero DB/IO dependency, per user story 22 — testable with raw HTML strings only. No knowledge of files, directories, or notebooks (that's `HTMLFileImportSource`'s job).

```python
@dataclass(frozen=True, slots=True)
class ParsedBlock:
    block_type: str   # a MarkdownBlockType.value
    payload: str

@dataclass(frozen=True, slots=True)
class ParsedNote:
    title: str
    blocks: list[ParsedBlock]
    skip: bool   # True => web.clip; caller must not persist anything

def parse_html_note(html: str, *, fallback_title: str) -> ParsedNote: ...
```

Rules (from the spec's Implementation Decisions, as updated above):
- Skip check first: `meta[itemprop=source]` content `== "web.clip"` → return `ParsedNote(title="", blocks=[], skip=True)` immediately, no further parsing.
- Title: first `<h1>` text if present (consumed, not also re-emitted as a `heading` block) → else `meta[itemprop=title]` content → else `fallback_title` (caller passes the file stem).
- `<h2>`–`<h6>` → `heading` block, level encoded in payload (e.g. `"## text"`).
- `<ul>`/`<ol>` → one `list_item` block per `<li>`, ordering marker encoded in payload text (`"- item"` vs `"1. item"`) since `MarkdownBlockType` has no ordered/unordered distinction. Flatten nested `<li>` to top-level list_item blocks (no nested-list support this iteration; leave a `# TODO` comment, symmetric with the table/image TODOs). Flattening is a structural simplification, not a skip — no placeholder involved.
- `<a href>` inside any block → rendered inline as `[text](href)`.
- **`<table>` and `<img>` → produce a single placeholder `paragraph` block** in-place (document order preserved), payload `"Skipped block: table"` / `"Skipped block: image"` respectively; comment `# TODO: table/image support (see spec Out of Scope)`.
- Everything else unhandled → `paragraph` block with the element's text content.
- Inline `style`/`class` attributes are always ignored (no placeholder — this is styling, not content).

Implementation: `BeautifulSoup(html, "html.parser")` — stdlib backend, no `lxml` needed. Add `beautifulsoup4>=4.12.0` to `pyproject.toml`'s `[project.dependencies]` (no HTML-parsing library exists anywhere in this repo today).

## Import abstraction (`src/assistant/adapters/import_source.py`)

A sibling to `ExternalSource` (`adapters/source.py`), for one-shot bulk imports into Notes rather than incremental RAG sync. Deliberately narrower than `ExternalSource`: no `since` cursor (a directory import is not incremental), and no `build()`/`ExternalSourceInstanceConfig`/`Registry` machinery — there is exactly one implementation this iteration, constructed directly by its CLI, so that config-driven-instantiation layer would be speculative. If a second `ImportSource` (e.g. an Evernote-backed one) is added later, a `Registry`-style resolver can be introduced then.

```python
@dataclass(frozen=True, slots=True)
class ImportedNote:
    """A single note ready for persistence, as returned by an ImportSource."""
    notebook_name: str
    parsed: ParsedNote  # from adapters.html_parser


class ImportSource(ABC):
    """Abstract base class for one-shot notes-import sources.

    Mirrors ExternalSource's list-then-fetch shape, but for bulk import into
    the notes system rather than incremental RAG document sync.
    """

    @abstractmethod
    def list_documents(self) -> list[str]:
        """Return identifiers for every document available to import."""
        ...

    @abstractmethod
    def get_note(self, document_id: str) -> ImportedNote:
        """Fetch and parse one document into a notebook name + storable blocks."""
        ...
```

## HTML file implementation (`src/assistant/adapters/plugins/html_file.py`)

```python
class HTMLFileImportSource(ImportSource):
    def __init__(self, root_dir: Path) -> None:
        self._root_dir = root_dir

    def list_documents(self) -> list[str]:
        """Each immediate subdirectory of root_dir is a notebook; each
        `*.html` file directly inside it (one level only — deeper nesting is
        ignored) is one document. Identifiers are paths relative to root_dir,
        e.g. "Personal/note1.html", which also encode the notebook name.
        """
        return [
            str(html_path.relative_to(self._root_dir))
            for entry in sorted(p for p in self._root_dir.iterdir() if p.is_dir())
            for html_path in sorted(entry.glob("*.html"))
        ]

    def get_note(self, document_id: str) -> ImportedNote:
        html_path = self._root_dir / document_id
        notebook_name = Path(document_id).parts[0]
        html = html_path.read_text(encoding="utf-8")
        parsed = parse_html_note(html, fallback_title=html_path.stem)
        return ImportedNote(notebook_name=notebook_name, parsed=parsed)
```

`list_documents` is where directory traversal happens (per point 4); `get_note` is where a single file is fetched and parsed into storable blocks. This mapping is exactly what a future `EvernoteImportSource` would replace: `list_documents` would call Evernote's notebook/note listing API instead of walking a directory, and `get_note` would fetch+convert one Evernote note (ENML or HTML export) instead of reading a file — the pipeline below stays unchanged either way.

## Pipeline (`src/assistant/adapters/notes_import.py`)

Mirrors `dataload.py`'s shape, but drives an `ImportSource` instead of an `ExternalSource`, and writes through `notes/service.py` instead of `Document`/vector store.

```python
@dataclass(frozen=True, slots=True)
class ImportStats:
    notebooks_touched: int
    notes_created: int
    notes_skipped_existing: int
    notes_skipped_web_clip: int
    notes_overridden: int

def compute_external_id(title: str) -> str:
    """Hash a note's title. Dedup uniqueness comes from pairing this with
    notebook_id at the query level, not from this hash alone."""
    return hashlib.sha256(title.encode("utf-8")).hexdigest()

def run_import(
    session: Session,
    import_source: ImportSource,
    owner_id: uuid.UUID,
    *,
    override: bool = False,
) -> ImportStats: ...
```

Per-document control flow inside `run_import` (modeled on `dataload.py:_process_document`'s dedup-by-composite-key shape):
1. `imported = import_source.get_note(document_id)`.
2. If `imported.parsed.skip` → count as `notes_skipped_web_clip`, no DB access at all.
3. `notebook = find_or_create_notebook(session, imported.notebook_name, owner_id)`.
4. `external_id = compute_external_id(imported.parsed.title)`.
5. `existing = get_note_by_external_id(session, notebook.id, external_id)`.
6. `existing is None` → convert `imported.parsed.blocks` to `(block_type, payload)` tuples, `create_note(..., external_id=external_id)`, then `add_markdown_node` per block in order, `session.commit()`, count as `notes_created`.
7. `existing is not None and not override` → count as `notes_skipped_existing` (no writes).
8. `existing is not None and override` → `replace_markdown_nodes(session, existing.id, owner_id, blocks)`, `session.commit()`, count as `notes_overridden`.

Wrap each document's processing in `try/except Exception: logger.exception(...)`, continue to the next → matches `_load_source_data`'s per-item resilience (dataload.py:119-130), so one malformed file doesn't abort the whole run. Commit **per note** (like `_process_document`, dataload.py:217) rather than once at the end: a crash mid-run leaves already-imported notes durably in place, and a re-run naturally resumes since already-imported notes are skipped as duplicates.

Never delete a `Note`/its nodes because a source document vanished — no code path does that; a subsequent run over a shrunken source simply doesn't revisit the missing document.

## CLI (`src/assistant/cli/import_html_notes.py`)

argparse, matching `add_evernote.py`'s shape (`main() -> int`, `if __name__ == "__main__": sys.exit(main())`, `get_session_factory()` for the DB session).

```
positional: root_dir (Path)
--email (required)
--password (optional; NOT required — see precedence below)
--override (store_true)
```

Password precedence — env var `NOTES_IMPORT_PASSWORD` (matches this repo's existing bare-SCREAMING_SNAKE_CASE convention, e.g. `JWT_SECRET`, not an app-wide-prefixed name):
```python
def _resolve_password(cli_password: str | None) -> str:
    env_password = os.environ.get("NOTES_IMPORT_PASSWORD")
    if cli_password is not None and env_password is not None:
        msg = "Password supplied via both --password and NOTES_IMPORT_PASSWORD; supply exactly one."
        raise ValueError(msg)
    if cli_password is not None:
        return cli_password
    if env_password is not None:
        return env_password
    return getpass.getpass("Password: ")
```

`main()`:
```
1. parse args
2. try: password = _resolve_password(args.password)
   except ValueError as exc: logger.error(str(exc)); return 1
3. with get_session_factory()() as session:
     try: user = authenticate_user(session, email=args.email, password=password)
     except AuthError: logger.exception("Authentication failed"); return 1
     import_source = HTMLFileImportSource(args.root_dir)
     stats = run_import(session, import_source, user.uid, override=args.override)
     logger.info("Import complete: %s", stats)
4. return 0
```
The ambiguous-password case gets its own explicit branch (not the generic `except Exception` fallback) so the CLI fails loudly and specifically per user story 13, rather than with a generic traceback.

## Test plan — TDD, three seams (per spec's Testing Decisions)

Follow `/superpowers:test-driven-development`: for each seam below, write the failing tests first (straight from the spec's user stories / Implementation Decisions), confirm they fail for the right reason (no implementation yet / import errors), then implement just enough to turn them green, then refactor. Do not write parser/pipeline/CLI code before its corresponding test exists and fails.

**`tests/adapters/test_html_parser.py`** — pure function, inline HTML strings, no DB/fixtures. Red-first cases: title-from-h1; title-falls-back-to-meta; title-falls-back-to-filename; web-clip skipped; non-web-clip source not skipped; `<ul>` → list_items; `<ol>` → list_items (ordering distinguishable from `<ul>` in payload); `<h2>`–`<h6>` → heading (parametrized); links preserved inline; `<table>` → placeholder paragraph `"Skipped block: table"` (in correct document position, not appended at the end); `<img>` → placeholder paragraph `"Skipped block: image"`; unhandled tag → paragraph; inline style/class ignored (no placeholder emitted for those); first `<h1>` consumed as title, not duplicated as a heading block.

**`tests/adapters/test_html_file_import_source.py`** — new seam (didn't exist in the prior plan revision), isolating `HTMLFileImportSource` from the DB pipeline: pure filesystem + parser, using `tmp_path` fixtures, no DB. Cases: `list_documents` returns one entry per `.html` file directly inside each subdirectory, sorted; files nested more than one level deep are excluded; `get_note` returns `notebook_name` equal to the immediate parent directory name; `get_note`'s `parsed` field matches what `parse_html_note` would return for that file's contents (i.e. it's a thin wrapper, not reimplementing parsing).

**`tests/adapters/test_notes_import.py`** — real `db_session` fixture (SQLite, `tests/conftest.py`) + a hand-rolled `_make_user` helper (matching `tests/notes/test_service.py:49-53`) + a real fixture directory `tests/adapters/fixtures/html_import/` (two notebooks, one `web.clip` note, one file nested a level too deep to prove it's ignored). Drives `run_import` against a real (test-double) `ImportSource` — either the real `HTMLFileImportSource` over the fixture directory, or a small in-memory fake `ImportSource` for cases that need to isolate pipeline logic from the filesystem (e.g. dedup/override behavior with hand-crafted `ImportedNote`s). Cases: creates notebooks from subdirectories; creates notes+nodes with correct external_id/ordering; reuses an existing notebook found by name (pre-created via `create_notebook` directly); skips `web.clip` notes entirely; a second run without `--override` produces no duplicates (row counts unchanged, `notes_skipped_existing` reflects it); `--override` replaces node content but keeps the same `Note.id`/`notebook_id`; deeper nesting ignored (via the real `HTMLFileImportSource`); two notebooks with same-titled note don't collide (proves the composite `(notebook_id, external_id)` key, not the hash alone); removing a source file between runs does not delete its previously-imported note; `create_notebook` called twice directly with the same name raises `DuplicateNotebookNameError`.

**`tests/cli/test_import_html_notes.py`** — `MagicMock` session/factory pattern (matching `tests/cli/test_add_evernote.py`), `run_import` and `authenticate_user` mocked/patched, no real DB. Cases: password from `--password`; password from env var (`monkeypatch.setenv`); password from interactive prompt when neither supplied (mock `getpass.getpass`); both `--password` and env var supplied → `main()` returns 1, neither `authenticate_user` nor `run_import` called; `--override` forwarded as `True`/defaults `False`; the authenticated user's `uid` (not email) is forwarded to `run_import`; a `HTMLFileImportSource` constructed from `root_dir` is what gets passed to `run_import`; `AuthError` from `authenticate_user` → `main()` returns 1.

Follow `AGENTS.md`'s Python test conventions throughout: module-level test functions (no test classes), `# --- Section ---` comment separators grouping related cases.

## Build order

1. Schema + migration helper (`schema.py`, `database.py`) — hard blocker for everything else. Sanity-check with `pytest tests/notes tests/adapters` immediately after.
2. `notes/exceptions.py` (`DuplicateNotebookNameError`) — trivial, unblocks service changes.
3. TDD: write failing tests in `tests/notes/test_service.py` for the new service functions, then implement `notes/service.py` additions. Can proceed in parallel with step 4.
4. TDD: write failing tests in `tests/adapters/test_html_parser.py` (add `beautifulsoup4` dependency first), then implement `adapters/html_parser.py`. Fully independent of steps 1–3.
5. TDD: write failing tests in `tests/adapters/test_html_file_import_source.py`, then implement `adapters/import_source.py` + `adapters/plugins/html_file.py`. Depends on 4.
6. TDD: write failing tests in `tests/adapters/test_notes_import.py` + build `tests/adapters/fixtures/html_import/`, then implement `adapters/notes_import.py`. Depends on 3 and 5.
7. TDD: write failing tests in `tests/cli/test_import_html_notes.py`, then implement `cli/import_html_notes.py`. Depends on 6's `run_import` signature.
8. `make check` (typecheck + lint + test) across everything touched.

## Verification

- `make check` must pass (mypy strict typing per `AGENTS.md`, ruff, full pytest suite) — this repo has no pre-existing failures relevant to this feature area (baseline run showed 259 passed / 4 pre-existing unrelated failures in eval/tui code).
- Manual end-to-end smoke test: `make services-up`, `python -m assistant.cli.setup_database`, create a test user via `python -m assistant.cli.api_client create-user ...`, register a password for it (check how `register_user`/`Credential` rows are seeded — via API or a small script), build a tiny fixture HTML directory by hand, then run `python -m assistant.cli.import_html_notes <dir> --email <email> --password <pw>`, and confirm via `python -m assistant.cli.api_client list-notebooks --user-id <uid>` / `list-notes` that the expected `Notebook`/`Note` rows exist. Re-run without `--override` and confirm no duplicates; re-run with `--override` and confirm node content changed, and that a table/image now shows up as a `"Skipped block: ..."` placeholder paragraph rather than being silently absent.
