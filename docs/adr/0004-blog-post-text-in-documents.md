# ADR-0004: Blog post text lives in the documents directory

## Status
Accepted

## Context
Each post of a blog source has metadata, an analysis and a full text. The
text is needed twice, both in the job: when the model summarizes the post, and
later, if the user marks the post useful, to embed it. It is never served by
the API, because the UI links to the original page and has no reader.

Fetching the page again at embedding time is not an option: the page may have
changed or gone, and feed-only text (a page that failed to download) can't be
recovered at all.

A single user's sources can produce thousands of posts of up to several
hundred kilobytes each, most of which nobody opens.

## Decision
- Save the text of every post, as UTF-8, at
  `<document_storage_path>/blog_posts/<post_id>.txt`, and never in Postgres.
- Write the file before calling the model, so a retry needs no new fetch and
  keeps feed-only text.
- Don't record in the database whether a file exists. The existence of the
  file is the answer.
- Delete files in one place only: a sweep at the end of each job run removes
  every file whose post no longer exists. Deleting a source, archiving it,
  deleting a user and a crash halfway through are all covered by that path, so
  they need no file handling of their own.

## Consequences
- **Pros**:
  - Rows stay small, so listing posts and `pg_dump` don't carry text no
    request reads.
  - `run_export` and `run_restore` already copy the whole documents directory,
    so backups include the text with no extra code.
  - One cleanup path, which can't be skipped by a code path that forgets it.
- **Cons**:
  - A deleted post's text stays on disk until the next run.
  - Files and rows can drift. A database restored without its documents
    directory has posts with no text, and those embed title and summary only.
    Nothing reports this.
  - A file write is not part of the database transaction. A crash between the
    two leaves an orphan (swept) or a post whose analysis retries (harmless).
  - Disk use grows with sources, because `not_useful` posts keep their text so
    a verdict can change without a fetch.

## Alternatives Considered
- **A `text` column on `blog_posts`**: transactional and simple, but it puts
  the largest and least read data in the most queried table and in every dump.
- **A separate `blog_post_texts` table**: keeps listings small, but dumps still
  grow, for data that is only ever read back by one job.
- **Keep only the text of useful posts**: saves disk, but moving a verdict to
  useful later would need a fetch, which the spec rules out.

## References
- `docs/specs/0008-blogs.md`
- `docs/plans/blogs.md`
- `docs/architecture/blogs.md`
