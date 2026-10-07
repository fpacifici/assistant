## Search

Users can find notes by keyword and by tag from the web UI, on desktop
and on mobile. A search returns the notes that match, each with the
sections (blocks) of the note that matched, so the user can jump straight
to them.

## Requirements

- Search covers every note the caller can **view**: notes they own, notes
  shared with them, and notes in notebooks shared with them. Being able to
  only list a notebook's notes is not enough, because results show content.
- Searchable content:
  - the note title (ranked higher)
  - the text of every block, with markdown syntax removed and link text kept
  - attachment file names
- Not searchable in v1: attachment contents and tag names as free text.
- A note is searchable as soon as the save that created or changed it
  succeeds. There is no indexing delay.
- Matching ignores case and accents (`perche` finds `perché`). There is no
  stemming.

## Query syntax

| Input | Meaning |
|---|---|
| `budget berlin` | notes containing both words, anywhere in the note |
| `"project plan"` | the words adjacent, in order |
| `berl` (last word) | prefix match while typing (`berlin`, `berliner`); only when the word is ≥ 2 characters |
| `tag:travel` | notes the caller has tagged `travel` (the caller's own tags) |
| `tag:"road trip"` | tag names with spaces |
| `tag:travel tag:2026 berlin` | several tags and words: all must match |

- The `tag:` prefix and tag names are case-insensitive.
- An empty query is rejected.
- A tag the caller doesn't have produces no results, and the response
  names it so the UI can say so.
- Not supported in v1: negation, `OR`, `notebook:`.

## Results

- Results are ordered by relevance (title matches first), with ties broken
  by most recently updated. A query with only tags is ordered by most
  recently updated. The caller can force `sort=updated`.
- 20 results per page, offset paging.
- Each result carries:
  - the note (title with matched words highlighted, notebook, the caller's
    tags)
  - up to 3 snippets, one for each matching block, each about 160
    characters around the match, with matched words highlighted
  - if no block matched (a title-only or tag-only match), the beginning of
    the note instead
- Highlights are returned as structured text segments, never HTML.

## UI

- **Desktop**: a search box in the header. Enter opens `/search?q=...`;
  the URL can be shared and bookmarked, and the back button works.
- **Mobile**: a search icon in the top bar opens a full-screen search
  view.
- Both layouts share one results list. Each result shows the title,
  notebook, tag chips and snippets, and has a "Load more" control. Empty
  results show an empty state; an unknown tag shows a message.
- Opening a result opens the note scrolled to the matched block, which
  flashes briefly. If that block no longer exists, the note opens at the
  top.

## Non-goals (v1)

BM25 ranking, vector/semantic search, searching attachment contents,
live results while typing, search from the agent or the TUI. The search
service interface is designed so these can be added without changing the
API.
