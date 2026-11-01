# Blogs

Implementation plan for [the blogs spec](../specs/0008-blogs.md): collect
blogs and feeds per user, summarize and score each post in a cron job, and
review them in a new Blogs tab.

Delivered as a stack of four PRs; each one passes `make check` (and
`make frontend-check`/`make frontend-test` when it touches the frontend) on
its own. Nothing is built until this plan is approved.

## Decisions

| Topic | Decision |
| --- | --- |
| Ownership | `owner_id` on directories and sources; posts reach their owner through the source. No `Entitlement`s: a service function loads the row filtered by owner and raises a not-found error otherwise. |
| Directories | New `blog_directories`. `Notebook` is not reused: it brings RBAC, notes and search with it. |
| Post identity | `post_key`, unique per source: SHA-256 of the guid, or of the URL path when there is no guid or the guid is a URL. The query string is kept only when it identifies the post (e.g. `?p=123`); `utm_*` and similar are dropped. |
| Collection window | `collect_since = now - lookback_days`, set at creation, never edited. No global setting. |
| Run cap | `blogs.max_posts_per_run` (default 50) per source, oldest first. |
| Discovery | Our own code on top of the safe fetcher: `feedparser` to test for a feed, BeautifulSoup (already a dependency) for `<link rel="alternate">`, `defusedxml` for sitemaps. |
| Extraction | `trafilatura.extract` and `extract_metadata` on HTML we downloaded. Its own downloading and discovery helpers are not used, because they bypass the fetcher. Falls back to the feed's `content:encoded` or summary. No headless browser. |
| Model call | One `init_chat_model(cfg).with_structured_output(PostAnalysis)` call, no `create_agent`, no tools. Text cut at 20 000 characters. Under 200 characters of text → `failed`, no call. |
| Language | Summary and motivation in the post's language. No config. |
| Tracing | `configure_tracing`; runs named and tagged `blog_process`, with `source_id` and `post_id` metadata. |
| Text | Not in the database. Saved at analysis time for every post, as UTF-8 at `<document_storage_path>/blog_posts/<post_id>.txt`. The subdirectory keeps these apart from the older files at the top level. `run_export` and `run_restore` already copy the whole directory, so backups include them. |
| Embedding | In the cron job, not the API. Reads the text file and never fetches. A post with no file embeds title and summary only. Whether a post has full-text chunks is the existence of its file, so no column records it. |
| Vector store | New Postgres-only table, not a langchain collection, same shape as `note_chunk_embedding`. |
| Pagination | Keyset, because evaluated cards leave the list and offsets would skip posts. |
| AI off | The UI hides the tab with the existing `useAskEnabled()`. The blog API itself is not gated. `process_blogs` exits with an error without `OPENAI_API_KEY`. |

## Data model

Migrations are in the PR that first uses the table.

```
blog_directories
  id, owner_id → users ON DELETE CASCADE, name, created_at
  UNIQUE (owner_id, name)

blog_sources
  id, owner_id → users ON DELETE CASCADE,
  directory_id → blog_directories ON DELETE SET NULL (nullable),
  url, feed_url, kind (feed | sitemap),
  title, remarks, preferences (nullable),
  collect_since, enabled, archived_at (nullable),
  etag, last_modified, last_fetched_at, last_error, consecutive_failures,
  created_at
  UNIQUE (owner_id, feed_url) WHERE archived_at IS NULL

blog_posts
  id, source_id → blog_sources ON DELETE CASCADE, post_key, url,
  title (nullable), published_at, created_at,
  summary, match_level (nullable), motivation (nullable),
  status (pending | processed | failed | skipped), attempts,
  state (new | useful | not_useful), evaluated_at (nullable),
  embed_status (none | pending | done | failed), embed_attempts
  UNIQUE (source_id, post_key)
  INDEX (source_id, state, published_at)

post_tags
  post_id → blog_posts ON DELETE CASCADE,
  tag_id → tags ON DELETE CASCADE, created_at
  PK (post_id, tag_id)

post_chunk_embedding (unmapped, added to _UNMAPPED_TABLES)
  langchain_id, content, embedding vector(1536),
  post_id → blog_posts ON DELETE CASCADE, source_id, owner_id,
  chunk_index, langchain_metadata jsonb
  HNSW cosine index
```

`status` is the pipeline; `state` is the user's verdict. `skipped` rows only
exist so a dateless or too-old sitemap URL is not fetched on every run; they
are never returned by the API. The `User` model cascades to the directories
and sources, so `delete_user` needs nothing else. `export.py` is a `pg_dump`
and needs no change.

Re-adding an archived source's feed is allowed by the partial unique index.
Its useful posts can then appear twice, once under each source. This is
accepted.

## Pipeline

`python -m assistant.cli.process_blogs [--user-id UID] [--source-id ID]
[--dry-run]`. `--dry-run` fetches sources and prints what it would collect,
without writing or calling a model.

1. Take a Postgres advisory lock. If it is held, exit 0.
2. **Collect**, for each enabled, non-archived source, sequentially, with a
   short delay between requests:
   - Conditional GET of `feed_url`. On 304, go to the next source.
   - Parse, compute `post_key`, drop keys already stored, drop posts older
     than `collect_since`.
   - For a sitemap, respect `robots.txt`, and for entries with no `lastmod`
     fetch the page for its date; store a `skipped` row if there is none.
   - Insert up to `max_posts_per_run`, oldest first, as `pending`/`new`,
     with feed text held in memory for step 3.
   - Save `etag` and `last_modified` only if nothing was left out by the
     cap. Otherwise the next run would get a 304 and never see the rest.
   - Update `last_fetched_at`, `last_error`, `consecutive_failures`.
3. **Analyze** each `pending` post, in its own transaction: if it has no text
   file, fetch the page, extract, fall back to feed text, and write the file.
   Then call the model and store the result. Writing the file first means a
   retry after a model failure needs no new fetch and keeps feed-only text.
   On failure increment `attempts`; at 3 the post is `failed`.
4. **Embed** each post with `embed_status = pending`: read the text file,
   chunk, embed. In the write transaction lock the post and check it is still
   `useful` with `embed_status = pending`, so a verdict changed while the job
   was calling OpenAI wins.
5. **Sweep** `blog_posts/`: delete each file whose post no longer exists.
   This is the only code that removes text files, so source deletion, archive,
   user deletion and crashes are all covered by one path, and a deleted post's
   text is gone after the next run.
6. Log failures (Sentry picks them up). Exit 1 if anything failed.

A source failure never stops the run.

## Safe fetcher

`blogs/fetch.py`, the only code that opens a URL. `fetch(url, *, etag,
last_modified) -> FetchResult`.

- Allows `http` and `https` only, and rejects URLs with credentials in them.
- Resolves the host, rejects loopback, private, link-local, multicast and
  reserved addresses, and connects to the validated address so a second DNS
  answer can't change the target.
- Follows redirects itself, at most 5, repeating the checks on each hop.
- Times out at 10 s and aborts past 5 MB while streaming.
- Sends a descriptive `User-Agent`.

Registration errors returned to the user are generic ("no feed found", "could
not reach this URL") and never include response content.

## Configuration

```yaml
ai:
  blog_model: openai:gpt-6-luna  # AI_BLOG_MODEL

blogs:
  summary_words: 50
  max_posts_per_run: 50
```

Read in `config.py` next to `ai.chat_model`.

## API

Routes in `api/routes/blogs.py`, mounted at `/blog`. The route handlers only
do HTTP work; everything else is in `blogs/service.py`.

| Route | Purpose |
| --- | --- |
| `GET, POST /blog/directory` | List, create |
| `PATCH, DELETE /blog/directory/{id}` | Rename, delete (sources move to Unfiled) |
| `GET, POST /blog/source` | List, register (runs discovery) |
| `GET, PATCH /blog/source/{id}` | Read (with `useful_post_count`), edit, pause, move |
| `DELETE /blog/source/{id}?keep_useful=` | Delete everything, or archive |
| `GET /blog/post?view=all\|relevant\|new&directory_id=&unfiled=&tag=&cursor=&limit=` | Post list, keyset |
| `PATCH /blog/post/{id}` | Set `state` (undo sets it back) |
| `POST /blog/post/bulk-state` | Set `state` on a list of ids, at most 500 |
| `POST /blog/post/{id}/tag`, `DELETE /blog/post/{id}/tag/{tag_id}` | Tag by id or name, untag |

Bulk action sends the ids of the cards on screen, so it can't hit posts the
user hasn't seen. Post responses never include `pending` or `skipped` posts.
The order is `published_at DESC, id DESC` for All and Relevant, and match
rank, `published_at DESC`, `id DESC` for New.

Setting `useful` sets `embed_status = pending`. Moving away from `useful`
deletes the chunks and sets `none`, in the same transaction.

## Stack

### PR 1: sources and directories backend

- Add `trafilatura`, `feedparser`, `defusedxml` to `pyproject.toml`; `make
  sync`.
- `models/schema.py`: `BlogDirectory`, `BlogSource`, `BlogPost` and their
  enums, `User` relationships, Alembic migration.
- `blogs/__init__.py`, `blogs/exceptions.py`, `blogs/fetch.py`,
  `blogs/discovery.py`, `blogs/identity.py` (`post_key`), `blogs/service.py`
  (directory and source CRUD, delete and archive).
- `api/routes/blogs.py` and `api/schemas` for directories and sources;
  register the router in `api/app.py`; map the new exceptions.
- ADR-0004: why post text lives in the documents directory and not in
  Postgres, and what that costs.
- Tests: fetcher (each blocked address class, a redirect to a private
  address, size limit, DNS mock), discovery with fixture HTML/XML (feed,
  advertised feed, sitemap, nothing), `post_key` cases (domain move, `?p=`,
  `utm_*`, guid as URL), ownership 404s, archive vs delete.

### PR 2: collection and analysis

- `blogs/extraction.py`, `blogs/text_store.py` (write, read, sweep),
  `blogs/analysis.py` (`PostAnalysis`, prompt, one call), `blogs/pipeline.py`
  (collect, analyze, sweep), `cli/process_blogs.py`, `make process-blogs`,
  config keys.
- Check `gpt-6-luna` works with `init_chat_model` and structured output. It
  has not been confirmed on this account. If it fails, stop and ask which
  model to use.
- Tests, with the fetcher and model mocked: dedupe, `collect_since`, each
  dateless case, run cap with the conditional-GET rule, retries to `failed`,
  thin content skips the model, no preferences means no motivation, the
  advisory lock, exit codes, the title fallback, a retry reuses the text
  file, the sweep removes only orphaned files.

### PR 3: evaluation, tags, embeddings

- Migration for `post_tags` and `post_chunk_embedding`; add to
  `_UNMAPPED_TABLES`.
- `blogs/service.py`: post list with keyset cursors, set state, bulk state,
  tag and untag (reusing `find_or_create_tag` and `get_tag` from
  `notes/tags.py`). Add the routes.
- `vectors/chunking.py`: pull the section splitting out of `chunk_note` so
  `blogs/chunking.py` can reuse it with a `Title / Source / Summary` header,
  with no change to note chunks.
- `blogs/store.py` for `post_chunk_embedding`; embedding step in the
  pipeline.
- Tests: keyset paging while posts leave the list, order of New, verdict
  transitions create and delete chunks, a verdict changed mid-embed wins, a
  missing text file falls back to title and summary, tags only reach the
  owner's posts.

### PR 4: frontend

- `api/blogs.ts`, `types`, routes in `routes.tsx`, `pages/BlogsPage.tsx`,
  `pages/BlogSourcesPage.tsx`.
- `components/blogs/`: `BlogDirectoryList`, `PostList`, `PostCard`,
  `SourceForm`, `DeleteSourceDialog`.
- Links in `DesktopHeader`, the mobile `⋯` menu and the TUI File menu, gated
  on `useAskEnabled()`.
- Split `TagEditor` so the chips and combobox take `tags`, `onAdd` and
  `onRemove`; notes behaviour and tests stay the same.
- Post links render only for `http(s)` URLs, with `target="_blank"` and
  `rel="noopener noreferrer"`.
- New styles use the theme tokens. Mobile follows the existing one-level
  pattern.
- Tests: three views, optimistic removal and undo, bulk confirm, delete
  dialog choices, unsafe URL not linked, failed-post card, mobile layout.
- `make frontend-check`, `make frontend-test`, and a run through the real app
  with a real feed.

## Documentation

With the code in each PR: `docs/architecture/blogs.md` (linked from
`AGENTS.md` and the architecture README), `api.md`, `frontend.md`,
`project_structure.md`, and the `process_blogs` command in the README.

## Risks

- **Disk use.** Text is kept for every post, including `not_useful` ones, so a
  verdict can change without a fetch. Posts are small, but the directory grows
  with the number of sources.
- **Files and rows can drift.** A restored or moved database without its
  documents directory leaves posts with no text, and those embed title and
  summary only.
- **Cron cost.** A long look back on a busy source costs up to
  `max_posts_per_run` model calls per run until it drains.
- **Extraction quality.** `trafilatura` varies by site. Failed posts stay
  visible, so gaps show up rather than disappear.
