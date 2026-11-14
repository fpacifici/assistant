## Reading list

Users save links to things they want to read or watch: web pages, PDFs,
text files and YouTube videos. The AI files each link under one of the
user's categories and writes a short summary. Once the user has read a
link, they either discard it to an archive or promote it to a note: a new
one, or an existing one suggested from their notes. The user writes the
note; the system only opens it.

Categories are shared with Blogs: today's blog directories become
categories with a description, and the description is what the AI reads
to choose one.

## Requirements

### Ownership

- Links and categories belong to one user. Nothing is shared and there
  are no entitlements.
- A user can only see or change their own data. Another user's item
  answers 404.
- Deleting a user deletes their links and categories.

### Categories

- Blog directories become **categories**. Existing directories keep their
  name and get an empty description.
- Categories are a single level. Each has a name, unique per user, and an
  optional description in natural language ("papers and posts about
  database internals").
- A blog source belongs to at most one category, chosen by the user, as
  today. A link belongs to at most one category, chosen by the AI and
  changeable by the user at any time.
- Items without a category appear under **Unfiled**.
- Deleting a category moves its sources and links to Unfiled.
- One **Manage categories** dialog, reachable from both the Blogs and the
  Reading tabs, creates, renames, describes and deletes categories. It
  marks categories that have no description.
- Changing a description affects new links only. Existing links are not
  re-categorized; the user can re-run the analysis of a single link.

### Links

| Field | Set by | Notes |
|---|---|---|
| URL | user | required, `http` or `https` |
| Title | system, editable | see [Titles](#titles) |
| Type | system | `web`, `pdf`, `text`, `youtube` or `other` |
| Category | AI, editable | nullable: Unfiled |
| Summary | AI | about 100 words, in the document's language; empty when not summarizable or failed |
| Notes | user | plain text, optional. A scratchpad on the link, never copied anywhere |
| Added | system | creation time |
| Note | system | the note it was promoted to, if any |

- The URL is normalized as blog post URLs are (tracking parameters such
  as `utm_*` and `fbclid` dropped). Adding a URL the user already has, in
  any state, is refused and points to the existing link.
- The content of the link is never stored: only the fields above.
- Links are added from an **Add link** box in the Reading tab, from the API,
  and from the API client CLI.

### Analysis

Analysis starts in the background as soon as a link is added. The link
appears at once, marked as being analyzed, and fills in when it is done.

| Analysis status | Meaning |
|---|---|
| `pending` | waiting for or under analysis |
| `done` | categorized and summarized |
| `not_summarizable` | categorized from title and URL only, no summary (YouTube, other types) |
| `failed` | could not be fetched or analyzed: no summary, Unfiled |

- The type is decided before any fetch for YouTube (by host:
  `youtube.com`, `www.youtube.com`, `m.youtube.com`, `youtu.be`), and from
  the response `Content-Type` otherwise.
- **Web pages**: the main text is extracted.
- **Text files** (`text/plain`, `text/markdown`): used as they are.
- **PDFs**: up to about 25 MB. Only the first pages are read, up to the
  input limit, and the model is asked to summarize from the abstract and
  introduction when present. The rest of the document is never read. A
  larger PDF fails.
- **YouTube**: title and channel only, through YouTube's oEmbed endpoint.
  Categorized, never summarized.
- **Other types** (images, archives, media files): categorized from title
  and URL, never summarized.
- The model only chooses among the user's existing categories, by name and
  description, or none (Unfiled). It never creates a category.
- Text is untrusted: the model call has no tools and only returns
  structured fields.
- A failed link stays in the list. The user can set the category and title
  by hand, or **Retry analysis**. Retry is also available on any analyzed
  link, for example after editing category descriptions.
- Fetching uses the same safety rules as blogs: public addresses only,
  limited redirects, time and size limits.

### Titles

In order: the page's `og:title` or `<title>`; a PDF's metadata title, then
its first line of text; the oEmbed title for YouTube; otherwise the URL.
The model's suggestion is used only when none of these exist. The user can
edit the title; a later retry never overwrites a title the user edited.

### States

| State | Meaning |
|---|---|
| `to_read` | new, or restored from the archive |
| `discarded` | in the **Archive** |
| `promoted` | turned into, or attached to, a note |

- **Discard** moves a link to the Archive. From the Archive it can be
  restored to *to read* or deleted.
- **Promote** is final: a promoted link cannot be promoted again or moved
  back. It can be deleted.
- There is no separate read flag: the decision is the signal that the link
  was read.

### Promoting

**Promote** opens a dialog:

- **Suggested notes**: up to 5 notes that talk about the same topic, found
  by semantic search over the user's notes with the summary as the query
  (the title for links without a summary). Only notes the user can edit
  are suggested.
- **Search**: a keyword search box to pick any other note the user can
  edit.
- **New note**: the user types a title and chooses a notebook where they can
  create notes.
- **Copy as markdown**: puts `[title](url)` and the summary on the
  clipboard.

Picking a note, or creating one, marks the link promoted, records the note,
and opens the note in the editor. **The system writes nothing into the
note**: a new note is empty apart from its title, and an existing one is
unchanged.

If the note is later deleted, the link stays promoted without a note.

### Reading tab

A new top-level tab **Reading**, next to Notes and Blogs, hidden when AI
is disabled like Blogs.

| Route | View |
|---|---|
| `/reading` | **To read**: links in `to_read`, one collapsible section per category (and Unfiled) with its count, oldest first |
| `/reading/archive` | **Archive**: discarded links, most recently discarded first |
| `/reading/promoted` | **Promoted**: promoted links, most recently promoted first, each linking to its note |

- A category sidebar jumps to or filters by a category, in every view.
- A card shows title, domain, type icon, added date, analysis status,
  summary, a category picker, the notes field, and the actions valid for
  its state: Open (the URL in a new tab), Promote, Discard, Restore, Delete,
  Retry analysis.
- On mobile the layout follows the [mobile layout spec](0006-mobile-layout.md),
  as Blogs does: the sidebar becomes a category picker.

## Out of scope

- A back-link from the note to the reading list.
- Writing the link, summary or notes into the note.
- Bookmarklets, browser extensions and mobile share targets.
- The AI proposing new categories.
- Storing or embedding link content.
- Summarizing videos (transcripts).
- Sharing links or categories with other users.
