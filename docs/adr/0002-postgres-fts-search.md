# ADR-0002: Keyword search on Postgres full text search behind a search service

## Status
Accepted

## Context
We need keyword and tag search over notes. Constraints:

- Notes must be searchable as soon as they are written or updated.
- The inverted index must live in plain Postgres (no separate search
  cluster, nothing on the API server's local disk).
- We don't want to implement ranking or an inverted index ourselves.
- Vector search may come later, so the client-facing interface must not
  depend on the engine.

We surveyed Python search libraries (October 2026). None of the maintained
ones keeps its index in Postgres and updates one document at a time:

- bm25s and rank_bm25 work in memory or on files and need full rebuilds.
- tantivy-py and pyserini store indexes on the filesystem.
- whoosh is unmaintained.
- Xapian is GPL and on-disk.

Postgres extensions that do provide BM25 add an operational dependency:

- pg_textsearch needs PG 17+, and we run 16.
- ParadeDB pg_search is AGPL.

## Decision
- Use Postgres built-in full text search: `tsvector` generated columns
  with GIN indexes on `nodes` and `notes`, `to_tsquery`, `ts_rank_cd`,
  and the `simple` config.
- Do tokenization and accent folding in Python, and use the same function
  for the index and the query. Postgres only sees pre-tokenized,
  space-separated words.
- Update the index in the same transaction as each note write, through a
  single hook (`index_note`, called from `_touch_note`).
- Hide the engine behind `assistant.search.service.search(...)`, which
  returns notes plus matching node snippets. The API, UI and future
  agent tool depend only on that.

## Consequences
- **Pros**:
  - No new dependencies or extensions.
  - Results are always consistent with the data.
  - Permission and tag filters are plain SQL joins.
  - Snippet and tokenizer logic is pure Python, so it's testable on SQLite.
- **Cons**:
  - The ranking is not BM25: `ts_rank_cd` ignores how rare a term is
    across notes and how long each note is.
  - No stemming, so "meeting" does not match "meetings" unless the user
    types a prefix.
  - Search queries need Postgres in tests (a `postgres` pytest marker).
  - Every note save also reindexes the note.

## Alternatives Considered
- **Own postings tables, PyStemmer for tokenizing, BM25 in SQL**: better
  ranking, but we would own the index upkeep and the scoring formula.
- **pg_textsearch**: real BM25 in Postgres. Rejected for now because it
  needs PG 17+ and an extension; this is the preferred upgrade path.
- **tantivy-py**: the best library overall, but its index lives on the
  filesystem and would need rebuilding and coordination across API
  workers.
- **ParadeDB**: rejected because of its AGPL license.
- **whoosh, rank_bm25, retriv**: unmaintained or no incremental updates.

## References
- `docs/specs/0007-search.md`
- `docs/plans/search.md`
- https://www.postgresql.org/docs/current/textsearch-controls.html
- https://github.com/timescale/pg_textsearch
- https://github.com/quickwit-oss/tantivy-py
- https://github.com/xhluca/bm25s
