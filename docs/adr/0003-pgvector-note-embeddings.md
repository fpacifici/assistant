# ADR-0003: Note embeddings in pgvector, written after commit

## Status
Accepted

## Context
The Ask AI agent answers questions from the notes a user can view, so the
notes need embeddings for semantic retrieval. Constraints:

- Notes change constantly (the web UI autosaves block by block).
- Embedding calls a paid remote API that can be slow, rate limited or out
  of credits. None of that may block or fail a note save.
- Retrieval must only return chunks of notes the asking user can view, and
  sharing changes must apply immediately.
- Postgres with pgvector is already deployed; we don't want another store.
- The previous pipeline embedded Evernote documents into langchain's legacy
  `PGVector` collection tables, outside the notes system and outside
  Alembic.

## Decision
- Store chunks in `assistant.note_chunk_embedding`, created by an Alembic
  migration in the app schema: `langchain_id`, `content`, `embedding
  vector(1536)`, `note_id` (FK to the note, ON DELETE CASCADE),
  `notebook_id`, `chunk_index`, and a JSONB `langchain_metadata` column for
  everything else. HNSW cosine index. The table is Postgres-only and not
  mapped in the ORM.
- Keep the layout compatible with langchain's v2 `PGVectorStore`, so the
  agent can use langchain retrieval (metadata filters on `note_id` /
  `notebook_id` columns, scores). Writes don't go through `PGVectorStore`,
  which commits row by row: the indexer replaces a note's chunks with
  SQLAlchemy in one transaction.
- Track freshness in an ORM-mapped `note_vector_index` table (content hash,
  index version, indexed-at, stale-since).
- Writes only mark notes stale, inside their transaction. After commit,
  an in-process background worker embeds them; repeated saves of a note
  coalesce, and an unchanged content hash skips the model call. Failures
  are logged and reported to Sentry, and the note stays stale for
  `reindex_search --vectors --stale-only`.
- Filter by permission at query time, from the entitlements: chunks whose
  notebook grants the user VIEW_NOTES/OWN_NOTES, or whose note grants
  VIEW_NOTE directly. Nothing about users is stored with the chunks.

## Consequences
- **Pros**:
  - Saving a note never waits for, or fails because of, the embedding API.
  - Sharing and unsharing apply to retrieval immediately.
  - The table is versioned with the rest of the schema; deleting a note
    deletes its chunks.
  - Burst edits cost one embedding call per note, and no-op saves none.
- **Cons**:
  - Embeddings lag writes by the worker's queue; in processes without a
    worker (CLI imports) notes stay stale until a reindex.
  - The queue lives in memory: jobs pending when the server stops are
    lost (the notes stay stale, so a reindex recovers them).
  - Changing to a model with another dimension needs a migration.
  - Filtered HNSW queries can return fewer than `k` results for users who
    can see only a small part of a large corpus.

## Alternatives Considered
- **Embed inside the write transaction**: simplest, but every autosave
  would wait on OpenAI and fail without credits.
- **langchain's legacy `PGVector` collections**: tables outside Alembic,
  a shared SQLAlchemy base that breaks when instantiated twice, and
  metadata filters on JSONB only.
- **A queue service (Celery, RQ)**: durable jobs, but a new deployment
  dependency for a single-node app; stale tracking in Postgres already
  makes lost jobs recoverable.
- **Per-user chunk copies or ACLs in metadata**: would have to be rewritten
  on every sharing change.

## References
- `docs/architecture/vectors.md`
- `docs/plans/vector_search.md`
