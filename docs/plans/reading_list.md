# Reading list

Implementation plan for [the reading list spec](../specs/0009-reading-list.md):
shared categories for blogs and links, a store of links categorized and
summarized by the AI in the background, and a Reading tab to triage them
and promote them to notes.

Delivered as a stack of four PRs; each one passes `make check` (and
`make frontend-check`/`make frontend-test` when it touches the frontend) on
its own. Nothing is built until this plan is approved.

## Decisions

| Topic | Decision |
| --- | --- |
| Categories | `blog_directories` renamed to `categories`, `description` added. `blog_sources.directory_id` renamed to `category_id`. API and UI rename "directory" to "category". Code moves out of `blogs/` into a new `categories/` package, since two features use it. |
| Ownership | `owner_id` on links, as on blog sources. A service function loads the row filtered by owner and raises a not-found error otherwise. No `Entitlement`s. |
| Package | New `src/assistant/reading/`: `service.py`, `analysis.py`, `extraction.py`, `worker.py`. API under `/reading/`, SPA at `/reading`. |
| Two status fields | `analysis_status` (`pending \| done \| not_summarizable \| failed`) is the pipeline, `state` (`to_read \| discarded \| promoted`) the user's decision, as `status`/`state` on blog posts. |
| URL identity | `url_key` = SHA-256 of the normalized URL, reusing the normalization in `blogs/identity.py` (tracking parameters dropped) but keeping the host: links come from many sites. Unique per owner. |
| When analysis runs | A `ReadingAnalysisWorker` thread in the API, started by the lifespan when AI is enabled, fed by an `after_commit` hook exactly like `VectorIndexWorker`. `python -m assistant.cli.process_reading` analyzes every `pending` link left over (restart, worker off). |
| Fetching | `blogs/fetch.py`, with a per-call `max_bytes`. 5 MB default, 25 MB when called for a link (the PDF case). The content type decides the extraction after the fetch. Move the fetcher to a shared module (`assistant/fetch.py`) since it now has two callers. |
| Web pages | `trafilatura` on the fetched HTML, as `blogs/extraction.py`. |
| PDFs | New dependency `pypdf`. Read pages in order until 20 000 characters, then stop. The prompt says the text is the beginning of a longer document and to summarize from the abstract and introduction. |
| YouTube | Host check before any fetch. `https://www.youtube.com/oembed?url=...&format=json` through the safe fetcher, for `title` and `author_name`. Categorize only: `not_summarizable`. |
| Other types | Categorize from title and URL: `not_summarizable`. |
| Too little text | Under 200 characters of extracted text: categorize from title and URL, `not_summarizable`, as blogs refuse to invent a summary. |
| Model call | One `init_chat_model(cfg).with_structured_output(LinkAnalysis)`, `ai.blog_model`, no tools. Input: title, URL, type, text (cut at 20 000 characters) and the categories as `id: name: description`. Output: `summary \| null`, `category_id \| null`, `title \| null`. A `category_id` not in the user's list is treated as null. |
| Summary length | `reading.summary_words: 100` (`READING_SUMMARY_WORDS`). |
| Tracing | `configure_tracing`; runs named and tagged `reading_process`, with `link_id` metadata. |
| Retries | `attempts` goes up on any failure; at 3 the link is `failed`. **Retry analysis** resets it to `pending` with `attempts = 0`. |
| User edits win | `title_edited` flag: an analysis never overwrites a title the user edited. A category the user set while analysis was running is kept: the write reloads the row and only sets `category_id` if `category_set_by_user` is false. |
| Note suggestions | `NoteSearcher` with the summary (or title) as query, more than 5 chunks fetched and grouped by note, keeping the first 5 notes. Filtered by a new `editable_scope(session, user)` in `notes/permissions.py`: notebooks with edit or own notes permissions and notes with a direct edit grant. |
| Keyword search in the dialog | Existing `/search` API, results the user cannot edit are greyed out client-side using the permissions already returned with notes. |
| Promotion | `POST /reading/link/{id}/promote` with either `{note_id}` or `{notebook_id, title}`. For a new note it calls `notes.service.create_note` (permission-checked there). It sets `state = promoted`, `promoted_at` and `note_id` in the same transaction and returns the note id. The client navigates to the note. Nothing is written into the note. |
| Note deleted | `note_id → notes ON DELETE SET NULL`. |
| AI off | The tab is hidden with `useAskEnabled()`. The API stays available; links added without AI stay `pending` until the CLI runs with a key. |
| Pagination | Keyset on the sort key of each view, as blogs: cards leave the list as they are decided. |

## Data model

```
categories                      (renamed from blog_directories)
  id, owner_id → users ON DELETE CASCADE, name,
  description (text, nullable)  -- new
  created_at
  UNIQUE (owner_id, name)

blog_sources
  category_id → categories ON DELETE SET NULL   -- renamed from directory_id

reading_links
  id, owner_id → users ON DELETE CASCADE,
  url, url_key,
  title (nullable), title_edited (bool),
  link_type (web | pdf | text | youtube | other, nullable until analyzed),
  category_id → categories ON DELETE SET NULL (nullable),
  category_set_by_user (bool),
  summary (nullable), user_notes (text, nullable),
  analysis_status (pending | done | not_summarizable | failed),
  attempts, last_error (nullable, generic message only),
  state (to_read | discarded | promoted),
  note_id → notes ON DELETE SET NULL (nullable),
  created_at, decided_at (nullable)
  UNIQUE (owner_id, url_key)
  INDEX (owner_id, state, category_id, created_at)
```

`decided_at` is set on discard and promote and cleared on restore. The
Archive and Promoted views sort by it.

## API

| Method and path | Purpose |
| --- | --- |
| `GET/POST /category`, `PUT/DELETE /category/{id}` | Categories (replaces `/blog/directory`) |
| `POST /reading/link` | Add `{url}`. 409 with the existing link's id on a duplicate. |
| `GET /reading/link?state=&category_id=&cursor=` | List a view |
| `GET /reading/link/counts?state=` | Count per category, for the section headers and sidebar |
| `PATCH /reading/link/{id}` | `title`, `category_id`, `user_notes` |
| `POST /reading/link/{id}/discard`, `/restore` | State changes. 409 when not valid from the current state. |
| `POST /reading/link/{id}/retry` | Back to `pending` |
| `GET /reading/link/{id}/suggestions` | Up to 5 editable notes with title, notebook and the matching passage |
| `POST /reading/link/{id}/promote` | See Decisions |
| `DELETE /reading/link/{id}` | From `discarded` or `promoted` only |

## PRs

### 1. Categories

- Migration: rename the table and column, add `description`.
- Move models and service functions to `categories/`. Rename the blog API
  and frontend types and components (`BlogDirectoryList` →
  `CategoryList`).
- `ManageCategoriesDialog` with description editing and a "no
  description" marker, opened from the Blogs tab.
- Update `docs/architecture/blogs.md`; new `docs/architecture/categories.md`.

### 2. Link store and API

- `reading_links` model and migration, `reading/service.py` (add,
  list, counts, update, discard, restore, delete), routes and schemas.
- URL normalization and duplicate detection.
- `api_client add-link` / `list-links`.
- No analysis yet: links stay `pending`.

### 3. Analysis

- Shared fetcher with per-call size limit; `pypdf` dependency.
- `reading/extraction.py` (type detection, HTML, text, PDF first pages,
  YouTube oEmbed), `reading/analysis.py` (prompt, `LinkAnalysis`, writes
  that respect user edits), `reading/worker.py`, lifespan wiring, retry
  route, `cli.process_reading`, config key.
- Tests mock the fetcher and the model; PDF fixtures built in the test with
  `pypdf`.
- New `docs/architecture/reading.md`.

### 4. Promotion and the Reading tab

- `editable_scope`, suggestions route, promote route.
- Frontend: `api/reading.ts`, `ReadingPage` with the three views,
  `LinkCard`, `AddLinkBox`, `PromoteDialog` (suggestions, search, new note,
  copy as markdown), the Reading tab in the header, routes, polling of
  `pending` links until analyzed, mobile layout, Manage categories entry.
- Vitest for the cards, the dialog and the routes.

## Risks

- **Large PDFs**: 25 MB is read into memory per analysis. The worker is
  single-threaded, so only one is in memory at a time.
- **Sites blocking fetches**: many pages (paywalls, logins, bot
  protection) will fail. They stay usable as plain links with a manual
  category, which is what the spec asks for.
- **Rename churn**: PR 1 touches most of the blog frontend. It ships alone so
  it can be reviewed as a pure rename plus one column.
