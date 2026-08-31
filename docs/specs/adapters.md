# Feature spec: Unify adapter layer and the new notes storage

## Problem Statement

The adapter layer described in [Adapters Layer](../architecture/adapters.md) only
knows how to import external documents into the RAG/vector-store pipeline — the
only adapter that exists today is Evernote, and everything it imports lands in
the `Document` table and vector store, never in the notes system described in
[Notes Service](../architecture/notesservice.md).

The product has since grown a full notes-taking system (with its own AI agent
and RAG on top of it), and there is no way to bring external notes — starting
with notes exported as HTML files — into that system as real, editable Notes.
Everything imported today is RAG-only content, invisible to the notes UI.

## Solution

Build a new HTML-directory adapter that scans a directory tree of exported HTML
notes (subdirectories become notebooks), parses each note into the
[MarkdownNode](../architecture/markdown.md) format, and writes it into the notes
database as a first-class `Note` — as if a user had created it directly. Import
runs through a CLI command that authenticates as the owning user, resolves or
creates notebooks by name, skips notes it has already imported (matched by a
new per-note `external_id`), and supports an explicit `--override` mode to
force re-import of already-seen notes.

The existing Evernote adapter and the RAG/`Document`/vector-store pipeline are
left fully intact in the codebase — they are only disconnected from this new
notes-import path, not removed, deleted, or migrated in this iteration.

---

## User Stories

1. As a notes-app user, I want my exported HTML notes imported as real Notes in
   my account, so that I can read, search, and edit them like anything else I
   created in the app.
2. As the person running the import, I want directories to become notebooks
   automatically, so that my existing note organization is preserved without
   manual re-filing.
3. As the person running the import, I want the first `<h1>` in a note to win
   as its title when present, so that the title matches what the note visibly
   says at the top of the page.
4. As the person running the import, I want the `meta itemprop=title` tag used
   as a fallback title when there's no `<h1>`, so that notes without a visible
   heading still get a sensible name instead of an empty title.
5. As the person running the import, I want notes marked `meta
   itemprop=source` = `web.clip` skipped entirely, so that web clippings (which
   aren't really "my notes") don't clutter my notebooks.
6. As the person running the import, I want bulleted and numbered lists
   preserved as lists, so that imported notes keep their original structure
   instead of collapsing into flat paragraphs.
7. As the person running the import, I want headings below the title (`<h2>`
   through `<h6>`) preserved as headings, so that imported notes keep their
   internal structure and are easy to navigate.
8. As the person running the import, I want links inside notes preserved, so
   that references to other pages or notes still work after import.
9. As the person running the import, I want to know that tables and images are
   not yet supported, and to see a clear placeholder marking where they were
   skipped rather than either mangled garbage paragraphs or silently missing
   content, so that I get a clean, honest note instead of corrupted or
   unexplained gaps.
10. As the person running the import, I want everything not explicitly handled
    to fall back to a plain paragraph, so that no content is silently lost even
    when the parser doesn't understand its original structure.
11. As the person running the import, I want to authenticate with my own
    account credentials when I run the CLI, so that imported notes end up owned
    by me and not some anonymous or shared account.
12. As the person running the import, I want to supply my password via an
    environment variable, a CLI argument, or an interactive prompt (whichever
    suits my situation), so that I can run the import both interactively and
    from scripts/cron.
13. As the person running the import, I want the CLI to fail loudly if I
    accidentally supply my password more than one way at once, so that I don't
    end up in an ambiguous or unintended auth state.
14. As the person running the import, I want notes I've already imported to be
    skipped on a normal run, so that re-running the import doesn't create
    duplicate notes.
15. As the person running the import, I want an explicit `--override` flag that
    forces already-imported notes to be replaced with the freshly parsed
    content, so that I can pull in upstream edits when I know I want them.
16. As a notes-app user, I want to understand that using `--override` discards
    any edits I made to the note inside the app since it was imported, so that
    I'm not surprised by losing my own changes.
17. As the person running the import, I want notes never to be deleted just
    because the source file disappeared, so that I don't lose data due to a
    reorganized or partially-copied source directory.
18. As the person running the import, I want notebook names to be unique
    across the system, so that two different import runs (or notebooks with
    the same name) can't quietly collide into confusing duplicates.
19. As the person running the import, I want directory nesting deeper than one
    level under a notebook directory to be ignored rather than silently
    flattened or mis-imported, so that unexpected directory structures don't
    produce surprising results.
20. As a developer maintaining the codebase, I want the old RAG/Document
    import pipeline left completely alone, so that reverting or re-enabling it
    later (e.g. for other, non-note sources) doesn't require reconstructing
    deleted code.
21. As a developer maintaining the codebase, I want the Evernote adapter left
    untouched and simply excluded from the new notes-import wiring, so that
    migrating it to notes-import can be scoped and done later without being
    entangled with the HTML-adapter work.
22. As a developer extending this feature later, I want the HTML block parser
    exposed as a pure, independently testable function (HTML in, `MarkdownNode`
    tree out), so that new parsing rules can be added and verified cheaply
    without needing a database.
23. As a developer extending this feature later, I want a documented seam for
    running the whole import pipeline against a fixture directory and a real
    test database, so that dedup/override/notebook-resolution behavior is
    verified end-to-end, not just in pieces.
24. As a future contributor, I want image and table support tracked as
    explicit TODOs rather than silently forgotten, so that the gap is visible
    and intentional, not an accidental oversight.
25. As a future contributor, I want the UI zip-upload import flow (importing a
    zip of HTML notes from the app itself) scoped as a distinct, later piece of
    work, so that this iteration can ship the CLI/parsing core without being
    blocked on upload/storage/extraction plumbing.

---

## Implementation Decisions

### Scope for this iteration

- The RAG/`Document`/vector-store pipeline is **not modified or deleted**. It
  is only disconnected from the notes-import path — no source routes through
  it anymore, but its code, schema, and the vector store remain in the
  codebase for potential future use.
- The **Evernote adapter is left as-is and excluded** from the new
  notes-import pipeline this iteration. It is not migrated, not deleted, and
  its existing RAG-import behavior (if invoked) is unaffected. Migrating it to
  notes-import (and deciding whether it stays on the live ENML API or moves to
  a manual HTML-export-based flow) is deferred to a later iteration.
- The **UI zip-file import flow** (uploading a zip of HTML notes from the app)
  is deferred entirely. This iteration ships the CLI-driven directory import
  only.

### HTML directory adapter

- Input is a root directory; each direct subdirectory is treated as one
  notebook. Directory nesting deeper than one level under a notebook directory
  is **ignored** — files further down are not scanned or imported.
- One HTML file = one note.
- Title resolution order: the first `<h1>` element's text wins if present;
  otherwise fall back to `meta itemprop=title`; otherwise fall back to the
  filename. The first `<h1>`, if used as the title, is consumed as the title
  marker and not also emitted as a heading block in the note body.
- A note is skipped entirely if `meta itemprop=source` has content `web.clip`.
- Block mapping:
  - `<ul>`/`<ol>` → `list_item` blocks (list style, ordered vs. unordered, is
    encoded in the block's markdown payload text, since the schema's
    `MarkdownBlockType` has no separate ordered/unordered type).
  - `<h2>`–`<h6>` → `heading` blocks.
  - Links are preserved inline within block text.
  - Tables and images are not rendered, but they are **not silently dropped**
    either: each produces a single placeholder `paragraph` block, in its
    original position, stating what kind of block was skipped (a table
    becomes a paragraph reading `Skipped block: table`; an image becomes
    `Skipped block: image`), so the note's structure and block count reflect
    the original content. Real table/image rendering remains a TODO for a
    future iteration (see Out of Scope).
  - This placeholder treatment applies only to element types the parser
    recognizes and deliberately does not render (currently: `table`, `img`).
    It does **not** apply to inline `style`/`class` attributes, which
    continue to be silently ignored throughout — a "skipped block"
    placeholder is about skipped *content*, not skipped *styling*.
  - Unhandled **container** elements (`div`, `article`, `section`, and the
    like) are recursed into rather than treated as opaque: their handled
    descendants still produce their normal structured blocks (headings,
    list items, table/image placeholders) in document order, and the first
    `<h1>` is consumed as the title wherever it sits in the tree, not only
    at the top level. Only genuinely unhandled *leaf* content — an element
    with no handled descendants — collapses to a single `paragraph`.
  - When a container mixes loose text directly inside it alongside at
    least one block-level child element (e.g. `<div>Some text<p>Body</p>
    </div>`), only the block-level children are emitted as blocks; the
    loose sibling text is not separately captured as its own `paragraph`.
    This matches real-world exports, where meaningful content is
    consistently wrapped in its own element rather than left as bare text
    beside a block sibling — bare stray text next to a block is treated as
    incidental whitespace/formatting, not content to preserve.
  - Everything else not explicitly handled → `paragraph`.
  - Inline styling (CSS) is ignored throughout.

### Data model changes

- `Note` gains an `external_id` column used for import dedup. For notes
  imported by the HTML adapter, this is a hash of the note's title, **scoped
  per notebook** (two notes with the same title in different notebooks don't
  collide; two notes with the same title in the same notebook do — matching
  the "two files with the same name cannot exist [in a directory]" constraint
  the source data already guarantees).
- `Notebook.name` gets a **global** uniqueness constraint (not scoped per
  owner) — noted as a "for now" decision; this may need revisiting if/when
  genuine multi-user notebook naming collisions become a real scenario.
- Notebooks are resolved find-or-create by name at import time.
- Note: a title/filename rename at the source changes the computed
  `external_id`, so a renamed note is treated as a new note on re-import; the
  old note is left in place (never deleted), not updated. This was an
  accepted tradeoff, not an oversight.

### Ownership and authentication

- The import CLI resolves the owning user by authenticating with an email and
  password against the existing `authenticate_user` function
  (`auth/service.py`) — no new auth mechanism is introduced.
- The password may be supplied via exactly one of: a CLI argument, an
  environment variable, or an interactive (non-echoing) prompt. If more than
  one is supplied in a given run, the CLI fails with an error rather than
  silently picking a precedence order.
- All notes and notebooks created by a given import run are owned by the
  authenticated user.

### Import / override semantics

- Default run behavior: a note whose `external_id` already exists in the
  database is skipped/ignored — only genuinely new notes are imported.
- `--override` flag: notes matched by `external_id` are **wholesale
  replaced** — all existing `MarkdownNode`s for that note are deleted and
  recreated from the freshly parsed source content. This is a blanket,
  run-wide flag, not selective per-note targeting.
- Notes and their nodes are **never deleted** by the importer, even if the
  corresponding source file disappears between runs (no deletion
  propagation).

---

## Testing Decisions

Tests should verify externally observable behavior (DB state, CLI output/exit
codes, parsed node structure) rather than internal call sequences, consistent
with this repo's existing adapter/notes tests.

- **Primary seam — full pipeline, real DB, real fixture files**: run the
  import pipeline end-to-end against an in-memory test database and a fixture
  directory of real HTML files (no mocking needed — unlike the existing RAG
  pipeline, there's no external vector store in this path). Assert resulting
  `Notebook`/`Note`/`MarkdownNode` rows, covering notebook resolution, dedup
  behavior, and `--override` replacement. Modeled directly on
  `tests/adapters/test_dataload.py`'s pattern of driving `load_data()` against
  a real DB and asserting real rows.
- **Secondary seam — pure HTML→MarkdownNode parser tests**: feed raw HTML
  strings directly into the parsing function and assert the returned node
  tree, to affordably cover the parsing-rule matrix (title precedence,
  `ul`/`ol`, heading levels, link preservation, table/image skip, `web.clip`
  skip) without paying for a full DB round-trip per case.
- **CLI seam — thin, matching existing convention**: mock the pipeline call
  itself; assert the CLI correctly resolves auth precedence (argument / env
  var / prompt, failing on more than one supplied) and forwards `--override`
  and the resolved user correctly. Matches the existing shallow style of
  `tests/cli/test_add_evernote.py`.
- Notes-service interactions (`create_note`, `create_notebook`) should reuse
  the existing `db_session` fixture and hand-rolled `User` pattern from
  `tests/notes/test_service.py` wherever the pipeline test needs to set up
  preconditions directly rather than through the importer itself.

This is three seams rather than the ideal of one; the split was proposed to
keep the parsing-rule matrix cheap to test without slowing down or bloating
the DB-level pipeline tests, and to preserve the repo's existing CLI-test
convention. See Further Notes.

---

## Out of Scope

1. Migrating the Evernote adapter to the notes-import pipeline (its content
   format, ENML vs. HTML-export, is a separate open design question).
2. The UI zip-file upload import flow (Goal 5 in the original spec framing).
3. Image support in the HTML parser (tracked as a TODO).
4. Table support in the HTML parser (tracked as a TODO).
5. Deletion propagation — deleting a `Note` because its source file was
   deleted or moved.
6. Per-owner scoping of notebook name uniqueness (currently global; flagged
   as a "for now" simplification).
7. Selective/targeted override (only a run-wide `--override` flag exists;
   there's no mechanism to force-override a specific note by id).
8. Handling of note renames as updates — a renamed source note currently
   imports as a new note rather than updating the old one in place.

## Further Notes

- The three-seam testing split (full-pipeline DB test, pure parser-function
  test, thin CLI test) was proposed during spec review and not explicitly
  re-confirmed after the proposal — it's the working plan, but worth a quick
  sanity check with the implementer before locking in the test layout.
- Passing the password as a plain CLI argument has known security tradeoffs
  (shell history, process-list visibility). It remains available as one of
  three explicit options because the user requested it; the environment
  variable and interactive-prompt options exist as safer alternatives for
  scripted and interactive use respectively.
- The global (not per-owner) uniqueness constraint on `Notebook.name` is a
  known simplification that doesn't fully hold up under genuine multi-user
  usage (two different users couldn't each have a notebook called "Personal").
  It was accepted "for now" and should be revisited if multi-user note
  ownership becomes a real, near-term scenario.
- Evernote's live API (`get_document` in `evernote.py`) only returns ENML, not
  HTML — there is no existing code path to fetch HTML from the live API.
  Evernote also offers a separate, manual "Export as HTML" feature whose files
  would match the new HTML-adapter's expected shape, but whether that export
  format carries a stable per-note identifier is unconfirmed and would need
  verification before Evernote is migrated to this pipeline.
