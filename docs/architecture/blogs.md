# Blogs

Users register blogs and feeds as sources. A job started from the command line
collects new posts, and the user reviews them in the Blogs tab. The behaviour
is in the [spec](../specs/0008-blogs.md). Code: `src/assistant/blogs/`.

Nothing is shared: directories and sources have an `owner_id`, posts reach
their owner through the source, and there are no entitlements. A service
function loads the row filtered by owner, so another user's row is a 404.

## Storage

| Table | Content |
| --- | --- |
| `blog_directories` | A user's single-level folders. `name` is unique per user. |
| `blog_sources` | What to collect (`feed_url`, `kind`, `collect_since`), the user's fields, and the last collection (`etag`, `last_modified`, `last_fetched_at`, `last_error`, `consecutive_failures`). Unique on owner and `feed_url` among sources not archived. |
| `blog_posts` | `post_key`, unique per source, metadata and analysis. `status` is the pipeline, `state` the user's verdict. |

Deleting a user cascades to all of it.

## Registering a source

`blogs/discovery.py` resolves the URL: as a feed, then a feed advertised with
`<link rel="alternate">`, then the site's sitemap (from `robots.txt`, or at a
well-known path). A page that declares itself an article (`og:type`, JSON-LD),
or that the feed lists as an entry, is a single post and is refused. Errors
are generic and never contain anything from the response.

## Deleting a source

`DELETE /blog/source/{id}` deletes the source with its posts. With
`keep_useful=true` the source is archived instead: it stops collecting, leaves
the source list, and only its useful posts stay. Its feed can then be
registered again, so a useful post can appear twice, once under each source.

## Safe fetcher

`blogs/fetch.py` is the only code that opens a URL.

- `http` and `https` only, no credentials in the URL.
- The host is resolved, every address must be public, and the connection goes
  to a validated address, so a second DNS answer can't change the target. TLS
  is verified against the host name.
- Redirects are followed by the fetcher, at most 5, with the same checks on
  each hop.
- 10 s for a whole request and 5 MB of decompressed body.

Fetched content is only parsed as data. Two details matter: `feedparser` gets
a stream, because given a plain value it tries it as a URL or a local path; and
sitemaps are parsed with `defusedxml`, with DTDs refused.

## Post identity

`blogs/identity.py`: `post_key` is the SHA-256 of the guid or, without one or
when the guid is a URL, of the URL path. The domain is ignored, so a blog can
move. Tracking parameters (`utm_*`, `fbclid`, ...) are dropped and any other
query parameter counts, which errs on the side of keeping two posts apart.
