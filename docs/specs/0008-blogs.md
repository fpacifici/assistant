## Blogs

Users register blogs and RSS/Atom feeds as sources. A background job
collects new posts and summarizes each one with a cheap model, explaining
how well it fits what the user wants from that source. The user reviews new
posts, marks the ones that are useful, and reads posts on the original site.

## Requirements

### Ownership

- Every user has their own directories, sources and posts. Nothing is
  shared and two users registering the same blog collect it separately.
- A user can only see or change their own data. Another user's item
  answers 404.

### Directories

- Directories are a single level. Each has a name, unique per user.
- A source belongs to at most one directory and can move at any time.
  Sources without a directory appear under **Unfiled**.
- Posts belong to their source and cannot move on their own.
- Deleting a directory moves its sources to Unfiled.

### Sources

| Field | Required | Notes |
|---|---|---|
| URL | yes | a feed, or a blog page |
| Title | no | defaults to the feed or page title |
| Remarks | no | free text for the user |
| Directory | no | |
| Preferences | no | natural language: what the user wants from this source |
| Look back (days) | no | default 7, 0 or more |

- Registration resolves the URL: try it as a feed, then look for a feed
  advertised on the page, then try the site's sitemap. If all fail, or the
  URL is a single post, registration fails with a clear error.
- A user cannot register the same resolved feed twice.
- Collection starts at `added time - look back days`. This date is set once
  and cannot be edited. Feeds may only list recent posts, so the form says a
  look back may return fewer posts than expected.
- A new source shows "Waiting for first collection" until the next job run.
- A source can be paused: collection stops and its posts stay.
- Changing the preferences affects new posts only.
- The source list shows the last error of a failing source. Failing sources
  are not disabled automatically.

### Deleting a source

The user chooses, in a dialog that shows the number of useful posts:

- **Delete everything**: the source, all its posts and their embeddings.
- **Keep useful posts**: the source is archived. It stops collecting and
  leaves the source list, its other posts are deleted, and its useful posts
  and their embeddings stay and still show the source name. An archived
  source appears in the post filters only while it has useful posts.

### Collecting posts

- A job started from the command line collects and processes posts. The
  system does not schedule it.
- A post is collected if it is not stored yet and its date is on or after
  the source's collection start. Posts already stored are dropped
  immediately and never reach the model again, and edits to them are ignored.
- A post is identified within its source by the feed's guid or, without one,
  by a hash of its URL path. The domain is ignored. The query string counts
  only when it identifies the post.
- A feed entry with no date counts as published when first seen. A sitemap
  entry uses `lastmod`, or the date found on the page. A sitemap post that
  still has no date is skipped and never fetched again.
- At most a configured number of posts per source are collected in a run,
  oldest first. The rest wait for the next run.

### Analysis

For each post the model produces, in the language of the post:

- a summary of about 35 words (configurable, for all users)
- a match level of `high`, `medium` or `low` against the source's preferences
- a short paragraph explaining that level (the motivation)

A source without preferences gets neither a match level nor a motivation.
The feed or page title wins; the model's title is used only if neither has
one. Posts too short to summarize are failed without calling the model, so a
summary is never invented from a title.

The model starts as `openai:gpt-6-luna` and is configurable. It has no tools,
because post text is untrusted. Runs are traced in LangSmith when it is on.

The post's metadata and analysis are stored in the database. Its full text is
stored as a file in the documents directory, never in the database, and is
deleted with the post by the next job run.

### Evaluation

- A post's state is `new`, `useful` or `not useful`, with the time it was
  evaluated. New posts start as `new`.
- **Relevant** always means the user marked the post useful. The model's
  match level never changes a post's state or hides it.
- A verdict can be changed at any time from any view.
- Separately from the verdict, a post can be marked **read**, and back to
  read later, at any time from any view, with the time it was read.
  New posts start unread. Opening a post does not mark it read.
- Marking a post useful embeds its title, summary and text, in a separate
  vector store from the notes. The job does this from the stored text, without
  fetching the page again. A post with no stored text embeds its title and
  summary only. The embeddings are not used by any feature yet.
- Moving a post away from useful deletes its embeddings.

### Collection history and refresh

For troubleshooting, every collection of a source is logged, by the job or by
hand, and the user can read it and refresh a source on demand.

- A run records when it started, what started it (the job or a refresh), how
  reading the source went (collected, not modified, failed with its error),
  and when its posts were done.
- For each entry the feed or sitemap listed: its link, title, date, how much
  text the feed gave, and the verdict: new post, already collected, older
  than the look back, left for the next run, no date (skipped for good), page
  unreadable (tried next run), blocked by robots.txt, or no usable link.
- For each post analyzed in the run: where its text came from (the page, the
  feed, or the text saved by an earlier attempt) and how long it was, then
  the outcome: summarized, too short, or failed with a generic error (tried
  next run, or given up). A summarized post shows the summary, match level
  and motivation the model answered then, even if the post changes or is
  deleted later. A post collected earlier and analyzed again is shown too.
- Only the latest 20 runs of a source are kept, and up to 300 entries of a
  run: posts collected by earlier runs are the first left out, and the run
  says how many entries the source listed in all.
- **Refresh now** collects one source immediately, without the conditional
  GET so the whole feed is listed, and analyzes its pending posts. The user
  watches the run fill in. It is refused while the job or another refresh is
  running, for a paused source, and when AI is disabled.
- A run cut short by a crash or a restart is shown as interrupted.

### Web UI

Notes and Blogs are top-level sections: the desktop header (also on the
Blogs pages in TUI mode) and the mobile `⋯` menu link to both, so the user can
always go back to the notes. The Blogs link, also in the TUI File menu, opens
Triage and is shown only when AI is enabled.

| Route | View |
|---|---|
| `/blogs/triage` | **Triage**: posts in the `new` state from every directory |
| `/blogs` | **All**: every post, newest first, with a directory sidebar including Unfiled |
| `/blogs/relevant` | **Relevant**: useful posts, same layout |
| `/blogs/sources` | Add, edit, pause and delete sources and directories |
| `/blogs/sources/:id/log` | **History** of one source: its runs, entries and the model's answers, with Refresh now |

- **Triage** shows every directory by default and can be filtered to one
  directory, or Unfiled, from a picker. Its tab always opens it on every
  directory.
- All and Relevant can be filtered by directory, by tag, and by read (to read,
  read, or both).
- A post card shows the title, source, date, summary, match level, motivation
  (when there is one), a Read badge once read, tag chips, Mark read / Mark to
  read, and Useful / Not useful buttons.
- The title opens the original post in a new browser tab. Opening a post does
  not change its state. There is no embedded reader.
- Lists scroll without limit.
- **Triage** is sorted by match level (high first, unscored last), then newest.
  An evaluated post leaves the list immediately, with a short undo. Under a read
  filter, a post marked otherwise leaves the list the same way.
- **Triage** offers "Mark visible as not useful" for the current directory, with
  a confirmation.
- Posts still waiting for analysis are hidden. Posts whose analysis failed
  are shown with their title and link and "Summary unavailable".
- Mobile shows one level at a time, like the rest of the app; Triage goes
  straight to the posts. TUI mode shows the desktop page.

### Tags

- Only posts have tags, applied by hand on the card in any view, from the
  same per-user vocabulary as notes. The model never sees them.

### Safety

- Every URL the server fetches goes through one fetcher: `http(s)` only, no
  loopback, private or link-local addresses (also after a redirect), with a
  timeout and a maximum size.
- Fetched content is only parsed as data. Nothing fetched is ever executed.
- The UI only links to `http(s)` post URLs and shows model output as text.

## Not in v1

- Sharing, directories inside directories, an embedded reader
- Tags on sources, generated tags
- Reprocessing posts, per-source model or summary length
- Pages that need JavaScript to render
- Any feature that reads the post embeddings
