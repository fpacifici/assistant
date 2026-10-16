# Vector search and the Ask AI tab

Embed the notes in pgvector as they are written, and let users ask an AI
agent questions answered from the notes they can view. Replaces the old
Evernote external-adapter pipeline, which embedded raw documents outside
the notes system.

Delivered as a stack of five PRs; each one passes `make check` (and
`make frontend-check`/`make frontend-test` when it touches the frontend) on
its own.

## Decisions

| Topic | Decision |
| --- | --- |
| Old pipeline | Delete the external-adapter flow (`adapters/{evernote,dataload,registry,source,secrets,content}.py`, the fake plugin, CLIs `add_evernote`, `load_data`, `load_note`, `generate_embeddings`, config `external_sources`, tables `documents`, `document_metadata`, `external_sources`). Keep the zip import, `html_parser` and the HTML-directory import source. |
| When to embed | After commit, in an in-process background worker. The write transaction only marks the note stale. Failures (no credits, quota, network) are logged as warnings with the exception, reported to Sentry, and leave the note stale for `reindex --vectors --stale-only`. |
| Storage | Alembic-created, Postgres-only `assistant.note_chunk_embedding` (`langchain_id uuid`, `content text`, `embedding vector(1536)`, `note_id uuid → notes ON DELETE CASCADE`, `notebook_id uuid`, `chunk_index int`, `langchain_metadata jsonb`, HNSW cosine index). Not ORM-mapped; excluded from autogenerate. Staleness lives in the ORM-mapped `note_vector_index`. |
| Library | langchain v2 `PGVectorStore` for retrieval (metadata filters, scores). Writes go through SQLAlchemy in the worker's own transaction, so a note's chunks are replaced atomically (`PGVectorStore` commits each inserted row separately). |
| Model changes | Same dimension: bump `VECTOR_INDEX_VERSION` and reindex. Different dimension: new migration. |
| Who sees what | Retrieval covers every note the asking user can view, computed at query time: `$or` of `notebook_id $in` (notebooks granting VIEW_NOTES/OWN_NOTES) and `note_id $in` (notes with a direct VIEW_NOTE grant). |
| Chunking | Render the note to markdown from its ordered blocks (attachments are their link text), split by markdown headers, then recursive 1000/200. Each chunk's embedded text starts with `Title: …` / `Notebook: …`. |
| Chunk metadata | `note_id`, `notebook_id` (columns), plus `notebook_name`, `title`, `created_at`, `updated_at`, `chunk_index`, `index_version` in the JSONB column. Tags are left out: they are per-user, and a shared note's chunks would leak the owner's tag names to everyone it is shared with. |
| Renames | Note title edits go through `_touch_note` already. A notebook rename marks all its notes stale. (Notes cannot be moved between notebooks today.) |
| Legacy store | Drop `public.langchain_pg_collection`/`langchain_pg_embedding` in the PR that replaces the agent; rebuild with reindex. Keep the langgraph checkpoint tables. |
| Agent | langchain `create_agent`, `openai:gpt-4.1`, `PostgresSaver` checkpointer. Tools, all run as the asking user: `search_notes` (vectors), `get_note` (full markdown), `keyword_search` (existing FTS). |
| Threads | Multi-turn, persisted by `PostgresSaver`; a `chat_thread(id, user_id, title, created_at)` table lists each user's threads. List, open, new, delete (deletes the checkpoints too). Title = first question, truncated. No rename. |
| API | SSE stream of `token`, `tool`, `sources`, `error`, `done` events. Sources (`note_id`, `notebook_id`, `title`, `notebook_name`) link to notes. A model failure is an `error` event, not a 500. |
| Models | `text-embedding-3-small` and `openai:gpt-4.1`, configurable under `ai:` in `config.yaml`. |
| AI off | No `OPENAI_API_KEY` → no embedding, the API answers 503, `GET /ask/status` reports `enabled: false` and the UI hides the Ask tab. No per-user rate limit. |
| LangSmith | Tracing only when `LANGSMITH_API_KEY` is set; project defaults to `Assistant` (`ai.langsmith_project`). Runs carry `user_id` and `thread_id` metadata. |
| UI | New `/ask` page (thread sidebar, streamed answer, source links). Linked from the desktop header ("Ask AI"), the mobile overflow menu and the TUI menu. |
| Evals | Fixture corpus in `data/evals/` (markdown notes in a few notebooks) loaded into an eval user; YAML dataset of ~10 questions incl. "not in the notes" ones; LLM-as-judge correctness + retrieval hit rate; `make eval` against LangSmith. **Never run in CI** — no tokens in the public repo. |

## Staleness

`note_vector_index(note_id PK → notes ON DELETE CASCADE, content_hash,
index_version, indexed_at, stale_since)`.

A note needs (re)embedding when it has no row, its `index_version` is older
than `VECTOR_INDEX_VERSION`, `indexed_at` is null, or `stale_since >
indexed_at`.

- `mark_notes_stale(session, note_ids)` upserts `stale_since = now()` and
  remembers the ids in `session.info`. It is called from `create_note`,
  `_touch_note` and (for every note of the notebook) a notebook rename.
- A global `after_commit` session listener hands the remembered ids to the
  registered listener (the worker's `enqueue`), if any; `after_rollback`
  drops them. Processes without a worker (CLIs, tests) just leave the notes
  stale.
- The worker records `indexed_at` as the time it *read* the note, so an
  edit committed while it was embedding keeps the note stale (and was
  enqueued again by its own commit).
- `content_hash` is the SHA-256 of the embedded chunk texts. When it is
  unchanged only the chunk metadata is rewritten; nothing is sent to OpenAI.

## Worker

`VectorIndexWorker`: one daemon thread, a FIFO of note ids plus a pending
set so repeated saves of one note collapse into one job. Each job opens its
own session, calls `index_note_vectors`, commits. Exceptions are caught,
logged with `logger.warning(..., exc_info=True)` and sent to Sentry. Started
and stopped by the FastAPI lifespan when AI is enabled; `stop()` drains
nothing (stale notes are picked up by reindex).

## Stack

1. **Remove the Evernote adapter flow** — code, CLIs, tests, config,
   `evernote-backup` dependency, docs; migration dropping `documents`,
   `document_metadata`, `external_sources`.
2. **Vector index** — `assistant/vectors/` (markdown rendering, chunking,
   store, indexer, worker, staleness), migration for `note_vector_index` +
   `note_chunk_embedding`, `ai` config, hooks in the notes service, worker
   in the API lifespan, `reindex_search --vectors`, `make reindex-vectors`,
   ADR 0003 + `docs/architecture/vectors.md`.
3. **Agent and Ask API** — new agent and tools, `chat_thread` table, chat
   service, `/ask` routes with SSE, LangSmith gating, TUI/`cli/chat`/
   `cli/query` on the new agent, migration dropping the legacy langchain
   tables, remove `agents/vectors.py`.
4. **Ask UI** — `/ask` page, API client with SSE parsing, header / mobile /
   TUI links, hidden when disabled, vitest tests.
5. **Evals** — corpus, dataset, loader, evaluators, `make eval`, docs.
