# Implementation plan: Keyword search

Adds keyword and tag search over notes. A single search string returns the
notes the caller can view, ranked, each with the sections (nodes) that
matched and highlighted snippets. Spec: [`docs/specs/0007-search.md`](../specs/0007-search.md).
Engine decision: [`ADR-0002`](../adr/0002-postgres-fts-search.md).

## Context

- A note is an ordered list of `Node`s (`src/assistant/models/schema.py:587`):
  `markdown` nodes (BlockNote blocks: paragraph, heading, list_item, …),
  legacy `text` nodes, and `attachment` nodes (`File.file_name`).
- Every note mutation in `src/assistant/notes/service.py` ends in
  `_touch_note(session, note_id)` (`service.py:372`): node add / insert /
  update / split / merge / delete, `replace_markdown_nodes` (used by the
  Evernote importer) and `update_note` (title). That is the single
  indexing hook.
- The web editor saves per node (`frontend/src/markdown/reconcile.ts`) and
  keeps a `ServerRegistry` mapping server node ids to BlockNote block ids.
- Tags are per user (`src/assistant/notes/tags.py`); a user only sees links
  to their own tags.
- Visibility: `can_view_notebook` / `require_note_access` in
  `src/assistant/notes/permissions.py` work on one subject at a time. There
  is no "all notes I can view" query yet.
- Tests build the schema with `Base.metadata.create_all()` on **SQLite**
  (`tests/conftest.py`). Postgres runs `pgvector/pgvector:pg16`
  (`docker-compose.yml`). Schema changes go through Alembic.

## Decisions

- **Engine: Postgres built-in full text search** (`tsvector`, GIN,
  `ts_rank_cd`) with the `simple` text search config. No new Python
  dependency, no Postgres extension. No BM25, no vector search for now:
  the search-service interface hides the engine (see ADR-0002).
- **Tokenization happens in Python, not in Postgres.** One function
  `analyze(text) -> list[str]` does: NFKD + strip combining marks (accent
  folding), `casefold()`, `re.findall(r"\w+")`. The index stores
  `" ".join(tokens)`, so Postgres' `simple` parser only ever sees clean
  words. The same function is applied to the query, so index and query
  can never disagree. No stemming (notes mix Italian and English).
- **Match at note level, snippet at node level.** All query words must
  appear somewhere in the note (title or body). The nodes shown as
  snippets are the ones matching *any* query word.
- **Indexed in the write transaction.** `index_note(session, note_id)` is
  called from `_touch_note`. No queue, no lag. Swappable for async later
  behind the same function.
- **Permissions inside SQL.** Search only returns notes the caller can
  *view* (snippets expose content, so `LIST_NOTES` on a notebook is not
  enough).
- **Snippets are built in Python**, not with `ts_headline`: the stored
  text is accent-folded, so `ts_headline` would show "perche" instead of
  "perché". Python strips the original payload to plain text, tokenizes it
  keeping offsets, and marks tokens whose folded form matches a query
  term. The API returns segments `[{text, highlighted}]`, never HTML.
- **Out of scope**: attachment contents, negation, `OR`, `notebook:`,
  live type-ahead results, BM25, vector search, agent/TUI wiring.

## PR 1: Index (schema, hook, backfill)

### 1.1 Schema (`src/assistant/models/schema.py` + Alembic migration)

ORM (portable, works on SQLite):

- `Node.search_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")`
- `Note.search_title: Text`, `Note.search_body: Text` (both `NOT NULL DEFAULT ''`)
- `Note.search_index_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")`

Postgres only, in the migration (not mapped in the ORM, so SQLite tests
are unaffected):

```sql
ALTER TABLE assistant.nodes ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (to_tsvector('simple'::regconfig, search_text)) STORED;
CREATE INDEX ix_nodes_search_vector ON assistant.nodes USING gin (search_vector);

ALTER TABLE assistant.notes ADD COLUMN search_vector tsvector
  GENERATED ALWAYS AS (
    setweight(to_tsvector('simple'::regconfig, search_title), 'A') ||
    setweight(to_tsvector('simple'::regconfig, search_body),  'B')
  ) STORED;
CREATE INDEX ix_notes_search_vector ON assistant.notes USING gin (search_vector);
```

`to_tsvector(regconfig, text)` is immutable, so generated columns are
allowed. The migration ends with a note that `reindex_search` must run
after upgrading (existing rows have empty `search_text`).

### 1.2 Analysis (`src/assistant/search/analysis.py`)

New package `src/assistant/search/`.

- `fold(text: str) -> str`: NFKD, drop `unicodedata.combining` chars, casefold.
- `analyze(text: str) -> list[str]`: `re.findall(r"\w+", fold(text))`.
- `tokens_with_offsets(text: str) -> list[tuple[str, int, int]]`: folded
  token + start/end offsets in the *original* text (for snippets).
- `markdown_to_plain(payload: str, block_type: str | None) -> str`: strips
  inline markdown (emphasis, code ticks, link syntax keeping link text,
  image syntax keeping alt text, HTML tags). Check
  `docs/architecture/markdown.md` and reuse an existing markdown helper if
  one exists before writing a new one.
- `SEARCH_INDEX_VERSION = 1`, bumped whenever any of the above changes.

### 1.3 Indexer (`src/assistant/search/indexer.py`)

- `node_search_text(node: Node, file_name: str | None) -> str`: markdown
  and text nodes → `" ".join(analyze(markdown_to_plain(...)))`; attachment
  nodes → analyzed `file_name`.
- `index_note(session, note_id) -> None`: loads the note's nodes (ordered)
  and their attachment file names in one query, sets each
  `node.search_text` that changed, sets `note.search_title`,
  `note.search_body` (nodes' texts joined) and
  `note.search_index_version = SEARCH_INDEX_VERSION`. Must `flush()`
  pending node changes first (service functions add the node and then call
  `_touch_note`).
- Call `index_note` from `_touch_note` in `service.py`. Importing from
  `assistant.search` into `notes.service` is fine; `search` must not import
  from `notes.service` (only `models` and `notes.permissions`) to avoid a
  cycle.
- Cost note: the editor saves per block, so every save reindexes the whole
  note. It's one ordered select plus updates of a few short columns per
  note, fine at note scale. If profiling shows otherwise, only re-analyze
  the touched node and rebuild `search_body` from stored `search_text`.

### 1.4 Backfill CLI (`src/assistant/cli/reindex_search.py`)

`python -m assistant.cli.reindex_search [--user-id UID] [--stale-only] [--batch-size 200]`

- Iterates note ids (all, or owned by the user), calls `index_note`,
  commits per batch, logs progress.
- `--stale-only`: only notes with `search_index_version < SEARCH_INDEX_VERSION`.
- Session handling per ADR-0001 (the CLI owns the session).
- Add a `make reindex-search` target.

### 1.5 Tests

- `tests/search/test_analysis.py`: folding (`perché` → `perche`,
  `Ærøskøbing`), casefold, punctuation, markdown stripping (links, code,
  emphasis, images), offsets map back to the original text.
- `tests/search/test_indexer.py` (SQLite): every service mutation (add,
  insert, update, split, merge, delete node, replace_markdown_nodes, title
  update, attachment) leaves `search_text` / `search_title` /
  `search_body` correct; version is set.
- `tests/cli/test_reindex_search.py`: backfill, `--user-id`, `--stale-only`.

## PR 2: Search service and API

### 2.1 Postgres test fixture

Search SQL uses `tsvector`, so it cannot run on SQLite.

- Add a `pg_session` fixture in `tests/conftest.py` that connects to the
  compose Postgres (`make services-up`), creates a throwaway database,
  runs `alembic upgrade head` on it (this also tests the migration), and
  drops it at the end.
- Mark these tests `@pytest.mark.postgres`. They skip with a clear message
  when Postgres is unreachable. Register the marker in `pyproject.toml`
  and document it in `docs/devenv.md`.
- Everything else (parser, snippets, indexer) stays on SQLite.

### 2.2 Query parser (`src/assistant/search/query.py`)

```python
@dataclass(frozen=True)
class SearchQuery:
    terms: tuple[str, ...]                 # analyzed words, AND
    phrases: tuple[tuple[str, ...], ...]   # analyzed tokens per phrase
    tags: tuple[str, ...]                  # normalized tag keys, AND
    prefix: str | None                     # last bare word, if len >= 2

def parse_query(raw: str) -> SearchQuery: ...
def to_tsquery(q: SearchQuery) -> str | None: ...   # None if no text part
def to_any_term_tsquery(q: SearchQuery) -> str | None:  # OR of all words, for snippet nodes
```

- Grammar: bare words; `"quoted phrase"`; `tag:name`, `tag:"multi word"`
  (case-insensitive prefix `tag:`); an unterminated quote runs to the end
  of the string.
- The last bare word becomes `prefix` (`word:*`) if the string doesn't end
  in whitespace and the word has ≥ 2 characters; otherwise it's a normal
  term.
- Bare words and phrase words go through `analyze`, so a bare word like
  `e-mail` becomes the two terms `e` and `mail`. Phrases become
  `a <-> b <-> c`.
- Tag names go through `tags.normalize_tag_name` (key part).
- Every lexeme is emitted single-quoted with quotes escaped, so user input
  never becomes tsquery syntax. Since `analyze` only yields `\w+`, the
  quoting is defence in depth.
- Raises `EmptySearchQueryError` when the parse yields no terms, phrases,
  prefix or tags.
- Tests: `tests/search/test_query.py` (pure, many cases including hostile
  input such as `' & | ! : * ( )`).

### 2.3 Viewable notes (`src/assistant/notes/permissions.py`)

`viewable_note_ids(caller: User) -> Select[tuple[uuid.UUID]]`: a
subquery of note ids where the caller has a note-level entitlement that
grants `VIEW_NOTE`, or a notebook-level entitlement on the note's
notebook that grants `VIEW_NOTES` / `OWN_NOTES` (expand roles via
`ROLE_PERMISSIONS` into the sets of role names and permission names that
qualify). Confirm in `docs/specs/0003_role_based_access_control.md` that
ownership is expressed as an entitlement; if not, OR `Note.owner_id ==
caller.uid` in. Tests on SQLite against `require_note_access` for every
role combination: the two must agree.

### 2.4 Service (`src/assistant/search/service.py`)

```python
class SearchSort(StrEnum): RELEVANCE = "relevance"; UPDATED = "updated"

@dataclass(frozen=True)
class SnippetSegment: text: str; highlighted: bool

@dataclass(frozen=True)
class Snippet: node_id: uuid.UUID | None; segments: tuple[SnippetSegment, ...]

@dataclass(frozen=True)
class SearchHit:
    note: Note
    score: float
    title_segments: tuple[SnippetSegment, ...]
    snippets: tuple[Snippet, ...]          # up to 3

@dataclass(frozen=True)
class SearchResults:
    hits: list[SearchHit]
    unknown_tags: list[str]

def search(session, caller, raw_query, *, offset=0, limit=20,
           sort: SearchSort | None = None) -> SearchResults: ...
```

Steps:

1. `parse_query`. Resolve `tags` to the caller's `Tag` ids (by
   `normalized_name`). If any key is unknown, return empty hits with
   `unknown_tags`.
2. Note query: `Note.id IN viewable_note_ids(caller)`; for each tag, an
   `EXISTS` on `NoteTag`; if there's a text part,
   `notes.search_vector @@ to_tsquery('simple', :q)`. The vector column
   isn't in the ORM, so use `literal_column("assistant.notes.search_vector")`
   or `sqlalchemy.column`. Keep the raw-SQL fragments in one module.
3. Order: `RELEVANCE` → `ts_rank_cd(search_vector, q) DESC,
   update_timestamp DESC`; `UPDATED` → `update_timestamp DESC`. Default
   sort is `RELEVANCE` with a text part and `UPDATED` for tag-only queries.
   Then `offset`/`limit`.
4. Snippet nodes for the page's note ids, in one query:
   `nodes.search_vector @@ to_any_term_tsquery`, top 3 per note by
   `ts_rank_cd` with `row_number() OVER (PARTITION BY note_id ...)`,
   ties broken by `position`.
5. Build segments in Python (`src/assistant/search/snippets.py`):
   `markdown_to_plain(payload)`, `tokens_with_offsets`, mark tokens equal
   to a term / phrase word or starting with `prefix`, cut a ~160-char
   window around the first highlight on word boundaries, add `…` at the
   cut ends, and merge adjacent segments.
6. Title segments: same highlighting on `note.title`.
7. No matching node (title-only match, or tag-only query): one snippet from
   the first non-empty text/markdown node, first ~160 chars, no
   highlights; `node_id` is that node, or `None` for an empty note.

Tests (`tests/search/test_service.py`, `@pytest.mark.postgres`):
words split across nodes match (note-level AND); accents and case;
prefix; phrase vs. scattered words; tags AND; unknown tag; tag-only sort;
permission matrix (owner, note share, notebook share, list-only notebook
role, no access, revoked); another user's tags don't apply; ranking puts
title hits first; pagination; snippet node selection and the 3-per-note
cap; title-only fallback. `tests/search/test_snippets.py` stays on SQLite
(pure).

### 2.5 API (`src/assistant/api/routes/search.py`, `api/schemas/search.py`)

`GET /search?q=...&sort=relevance|updated&offset=0&limit=20`
(`pagination_params`, max limit as elsewhere).

```json
{
  "results": [
    {
      "note": { "...": "NoteResponse, including the caller's tags" },
      "notebook": { "id": "…", "name": "…" },
      "score": 0.42,
      "title": [{ "text": "Trip to ", "highlighted": false }, { "text": "Berlin", "highlighted": true }],
      "snippets": [{ "node_id": "…", "segments": [ … ] }]
    }
  ],
  "unknown_tags": [],
  "offset": 0,
  "limit": 20
}
```

- 400 on `EmptySearchQueryError`. The route only parses, calls
  `search.service.search`, and serializes (AGENTS.md API convention).
  Reuse `_note_response` / the tags batch loader (`tags_for_notes`) so
  tag chips cost one query per page.
- Tests in `tests/api/test_search.py` (`postgres` marker): 400, shape, auth.
- Update `docs/architecture/api.md`; add `search` to the API client CLI
  (`python -m assistant.cli.api_client search --q ...`).

## PR 3: Web and mobile UI

Follow `docs/architecture/frontend.md` and `docs/specs/0006-mobile-layout.md`.

- `frontend/src/api/search.ts`: typed client for `GET /search`.
- Route `{ path: '/search', element: <Layout /> }` in `routes.tsx`, with
  the query in `?q=` (shareable, back button works). React Query key
  `['search', q, sort, offset]`.
- `SearchBox` component:
  - Desktop: in `DesktopHeader`. Enter navigates to `/search?q=`; it
    doesn't submit when empty/whitespace.
  - Mobile: a search icon in `MobileTopBar` opens a full-screen search view
    (input autofocused, results below, back closes it).
- `SearchResults` component (shared by both layouts): title with
  highlights, notebook name, tag chips (reuse the note-list chip
  component), up to 3 snippets rendered from segments with `<mark>` (text
  nodes only, no `dangerouslySetInnerHTML`), "Load more" for paging,
  empty state, and an "unknown tag" message from `unknown_tags`. A
  `tag:` chip click searches `tag:"name"`.
- Clicking a result navigates to
  `/notebooks/:nb/notes/:id?node=<node_id>`. In `NoteEditor`, after the
  document loads, map `node` through `ServerRegistry` to the BlockNote
  block id, scroll it into view, and flash a highlight CSS class for
  about 1.5s. If the node is missing, open at the top. Remove the `node`
  param afterwards (`replace` navigation) so a reload doesn't scroll again.
- Tests (Vitest + RTL): segment rendering escapes HTML; empty query not
  submitted; desktop and mobile layouts render the box (`?layout=mobile`);
  result click URL; editor scroll-to-node with present and missing node;
  unknown-tag message.
- Update `docs/architecture/frontend.md`.

## Docs

- PR 1: `docs/architecture/notesservice.md`: the search columns in the
  ER diagram, the "index on touch" rule.
- PR 2: `docs/architecture/api.md`, a new `docs/architecture/search.md`
  (pipeline: analyze → index → parse → match → snippets), linked from
  `docs/architecture/README.md` and `AGENTS.md`.
- PR 3: `docs/architecture/frontend.md`.

## Rollout

1. Deploy PR 1, then run `python -m assistant.cli.reindex_search`.
2. Deploy PR 2. Search is reachable via API/CLI only.
3. Deploy PR 3.

Any later tokenizer change: bump `SEARCH_INDEX_VERSION`, deploy, then run
`reindex_search --stale-only`.

## Future work (keep the interface)

- BM25: `pg_textsearch` (needs PG 17+) or our own postings tables. Swap
  the match/rank step in `search.service` only.
- Vector / hybrid search over the existing PGVector store, merged with the
  keyword results inside `search()`.
- Attachment contents, `notebook:`, negation/`OR`, live type-ahead, an
  agent tool and a TUI command on top of `search()`.
- Async indexing, if writes get slow: replace the body of `index_note`
  with an outbox insert.
