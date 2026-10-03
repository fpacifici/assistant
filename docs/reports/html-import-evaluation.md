# Evaluation: HTML notes import (PR #38) against the real Evernote export

Date: 2026-10-03
Input: `~/Documents/notes` (Evernote 11.20.2 export, 36 notebooks, 1392 `.html` notes)
Code under test: `HTMLFileImportSource` + `parse_html_note` (`src/assistant/adapters/`), run
without a DB. The Markdown for each note is the title plus the block payloads in order.

## Method

1. Ran `HTMLFileImportSource.list_documents()` / `get_note()` over the whole export.
2. Picked 95 random notes from the ones the importer does not skip, in two rounds with no
   overlap: 20 notes (seed `20261003`, reviewed by hand) and then 75 more (seed
   `202610032`). The second round was checked by script (step 4), and every flagged
   difference was confirmed by reading the note.
3. For each note, built an independent reference rendering of the HTML that keeps the
   visible structure: nesting depth, bold/italic, checkbox state, tables and attachments.
   It honours Evernote's CSS. For example, the `<input type=checkbox>` inside every `<li>`
   only shows when the list is `ul.en-todolist`. The reference was cross-checked against
   WebKit's text rendering (`textutil`).
4. Diffed the reference against the importer's Markdown. Then classified each difference as
   a layout mismatch, missing content or wrong layout. Attachments are excluded. For the
   second round the script also lists any difference it can't classify; the only ones it
   found were attachment captions.
5. Ran two scripted checks over **all** 886 imported notes, to cover rare features
   that no sampled note contains (tables, legacy checkboxes):
   - how often each structural feature appears;
   - a word-level check for text in the HTML that is missing from the Markdown.

## Headline numbers

| | |
|---|---|
| Notes in export | 1392 |
| Skipped entirely as `web.clip` | **506 (36%)** — mostly `architecture` (145), `diststream` (74), `system design` (66), `main` (64) |
| Imported | 886 |
| Parse errors | 0 |
| Sample size | 95 (20 + 75) |
| Sample notes that match the HTML exactly | **43 / 95 (45%)** |
| Sample notes with only minor issues (empty bullets, dead links) | 8 / 95 |
| Sample notes with a layout mismatch | **44 / 95 (46%)** |
| Sample notes with missing text | **0 / 95** (the bug in finding 1 exists but no sampled note hit it) |

How often each issue appeared in the sample:

| Issue | Notes (of 95) | Share | Across all 886 imported notes |
|---|---:|---:|---:|
| Nested list flattened | 39 | 41% | 366 (41%) |
| Empty `- ` bullet | 14 | 15% | 146 (16%) |
| Bold section headers become plain text | 4 | 4% | 79 have bold/italic (9%) |
| Other inline formatting lost (bold, inline code) | 4 | 4% | (included above) |
| Attachment caption shown as text | 3 | 3% | 54 (6%) |
| Dead links to other notes | 3 | 3% | — |
| Words glued together in list items | 2 | 2% | 8 |
| Checkbox state lost | 1 | 1% | 28 + 9 legacy |
| Nested numbered list renumbered | 1 | 1% | 24 have `<ol>` |
| Text lost | 0 | 0% | ~10 notes (finding 1) |

The sample rates are close to the rates across all imported notes, so the sample is
representative.

## Results after the fixes

The fixes in [`docs/plans/html-import-fidelity-fixes.md`](../plans/html-import-fidelity-fixes.md)
(one commit per step) were re-measured with `scripts/eval_html_import.py` (see
"Re-running the evaluation"). That script compares the HTML with the importer's
Markdown *as loaded by a Markdown parser*, so it also catches payloads that would load
as the wrong structure. "Before" is the same script run against the parser before the
fixes. It is stricter than the hand review above (it counts escaping and spacing), so its
"before" clean count is 41 rather than 43.

| | Before | After |
|---|---:|---:|
| Sample notes that match the HTML (of 95) | 41 | **92** |
| Imported notes that match the HTML (of 886) | 365 | **851** |
| Notes with words missing from the import (of 886) | 25 | **0** |
| Notes with nested lists flattened | 365 | 0 |
| Notes with empty bullets | 152 | 0 |
| Notes with formatting lost or different | 78 | 1 |
| Notes with checkbox state lost | 14 | 0 |
| Notes with nested numbered lists renumbered | 8 | 0 |
| Notes with tables dropped | 2 | 0 |
| Notes showing `Untitled Attachment` as text | 54 | 0 |

The 35 imported notes that still differ:

- **33 `Evernote_index` notes:** their links point to other notes' `.html` files. These are
  the dead links between notes, which are out of scope until the app has links between
  notes.
- **`diststream/A simple explanation of Bitcoin “Sidechains”`:** bold inside italic is written
  as `*a **b** c*` rather than `*a* ***b*** *c*`. Both render the same.
- **`system design/Counting Objects`:** italic around inline code (`<i><code>`) keeps the
  code and drops the italic.

### Web clips (`--include-web-clips`)

Web clips are still skipped by default, as the spec intends. With `--include-web-clips` all
1392 notes import with no errors, and **359 of the 506 clips** match the HTML. Over a random
sample of 20 clips (`--only-web-clips --sample 20 --seed 2026`), 14 match. All 6 differences
are lines that the clipped page separates only through CSS (e.g. a `<span>` styled as a
block), which the importer joins into one paragraph. No text is lost.

Across all clips, the remaining differences are:

- **Joined lines (about 140 clips):** CSS-only line breaks, as above.
- **Glued words (19 clips):** words the page separates only with CSS spacing. Examples are
  adjacent button links (`Read the docs` + `fully…`) and a hex dump laid out as a grid of
  spans.
- **Numbering (2 clips):** code shown as an `<ol>` with one `<li>` per line. Blank lines are
  empty items, which are dropped, so the line numbers shift.

## Per-note results

### Round 1 (20 notes, reviewed by hand)

| # | Note | Blocks | Result | Issues |
|---|------|-------:|--------|--------|
| 1 | AI/Notes on building agents | 42 | Layout | 3-level nested list flattened (24 sub-items shown as top level) |
| 2 | infrastructure/Slack network infra | 10 | Layout | Nested item flattened; trailing empty `- ` bullet |
| 3 | AI/Agentic code factory | 7 | OK | — |
| 4 | architecture/From Backbone to React… | 1 | OK | — |
| 5 | Investments/ETF strategy | 3 | OK | — |
| 6 | system design/Large files | 9 | Layout | 3 sub-items flattened |
| 7 | diststream/Distributed GHT | 1 | OK | — |
| 8 | Trips/San Francisco Food | 71 | Layout | Bold section labels (`Breakfast`, …) become plain paragraphs; 8 groups of sub-items (hours/price under each winery) flattened; 2 empty bullets |
| 9 | diststream/Kafka | 1 | Layout | PDF-only note; the attachment card's caption `Untitled Attachment` is emitted as a paragraph |
| 10 | DBstorage/Timeseries encodings | 4 | Minor | Trailing empty bullet |
| 11 | languages/State vs Strategy… | 2 | OK | — |
| 12 | architecture/mastercard | 1 | OK | — |
| 13 | diststream/Is Parallel Programming Hard… | 1 | OK | — |
| 14 | Trips/Vienna ristorante | 21 | Layout | Restaurant names and their details are at the same level, so you can't tell which detail belongs to which restaurant; 2 empty bullets |
| 15 | Costa Rica/Monteverde | 8 | OK | — |
| 16 | AI/Evernote_index | 65 | Wrong links | 65 note-to-note links point to `xxx.html` from the export and are dead once imported |
| 17 | main/Cully meeting | 15 | Layout | Nested items flattened |
| 18 | cucina/Wellington | 30 | Layout | Recipe steps and sub-steps (2 levels) flattened |
| 19 | architecture/httpciteseerx… | 0 | OK | Title-only note |
| 20 | recr/Interview scheduling status | 34 | Layout | 9 bold company headers become plain paragraphs; nested status items flattened |

### Round 2 (75 notes, checked by script and confirmed by reading)

| # | Note | Blocks | Result | Issues |
|---|------|-------:|--------|--------|
| 21 | AI/MCP | 18 | Layout | 5 nested items flattened |
| 22 | recr/Projects to build | 28 | Layout | 2 nested items flattened; 5 bold section headers become plain text |
| 23 | DBstorage/Redis notes | 4 | Layout | 3 nested items flattened |
| 24 | Sentry/The Infra onboarding plan | 5 | Layout | 1 nested items flattened |
| 25 | real estate/333 Freemont | 43 | Layout | 17 nested items flattened |
| 26 | AI/How to scale models | 60 | Layout | 31 nested items flattened; 1 lines lose bold/inline code; 1 empty bullet |
| 27 | DBstorage/Postgres schema notes | 11 | Layout | 2 lines lose bold/inline code; 1 empty bullet |
| 28 | architecture/perf | 21 | OK | — |
| 29 | diststream/Distributed async-await | 31 | Layout | 12 nested items flattened |
| 30 | Sentry/Armin | 17 | Layout | 10 nested items flattened |
| 31 | DBstorage/PingCap TiDB | 3 | OK | — |
| 32 | system design/Tracing papers | 2 | OK | — |
| 33 | diststream/httpsaphyr.composts283-call-me-maybe-redis | 0 | OK | title-only note (nothing to compare) |
| 34 | Sentry/Roundtable | 7 | Layout | 3 nested items flattened |
| 35 | AI/httpwww.nextplatform.com20160907next-wave-deep-learnin… | 1 | OK | — |
| 36 | Investments/Fidelity meeting (3) | 21 | Layout | 4 nested items flattened |
| 37 | cucina/Dinner | 38 | OK | — |
| 38 | system design/SSD storage | 1 | OK | — |
| 39 | algorithms/[interviews] Arrays Strings Hash Lists | 6 | Minor | 1 empty bullet |
| 40 | ISF/Installing puppet | 1 | OK | — |
| 41 | Investments/Bonds | 2 | OK | — |
| 42 | Investments/Health insurance | 38 | Layout | 22 nested items flattened; 10 lines lose bold/inline code; words glued together (`procedureNot`, `experimentsdifferent`) |
| 43 | cucina/Tagliolini granchio | 6 | OK | — |
| 44 | recr/HTTP server | 18 | Layout | 13 nested items flattened; nested numbered lists renumbered as one continuous sequence (1–13) |
| 45 | real estate/MB360 1200 4th | 34 | Layout | 13 nested items flattened |
| 46 | Trips/Cote d'azur | 10 | Layout | 6 nested items flattened |
| 47 | Investments/Fidelity meeting (1) | 15 | Layout | 4 nested items flattened; 1 empty bullet |
| 48 | Investments/Options | 26 | OK | — |
| 49 | architecture/Note conflict httpblog.soat.fr20130902-jvm-h… | 1 | OK | — |
| 50 | diststream/httpsjepsen.ioconsistency | 1 | OK | — |
| 51 | Investments/Goal | 15 | OK | — |
| 52 | cucina/Wines | 5 | OK | — |
| 53 | architecture/Microsoft wuantum computing | 1 | OK | — |
| 54 | languages/Dimensional analysis | 1 | OK | — |
| 55 | languages/C++ todo | 9 | Layout | words glued together (`procedureNot`, `experimentsdifferent`) |
| 56 | languages/httperlang.orgdocdesign_principlesdes_princ. | 0 | OK | title-only note (nothing to compare) |
| 57 | diststream/Spark Streaming Architecture | 33 | Layout | 11 nested items flattened; 1 empty bullet |
| 58 | DBstorage/Iceberg native DBs | 15 | Layout | 4 nested items flattened |
| 59 | Sentry/Notes from ingest | 25 | Layout | 6 nested items flattened |
| 60 | AI/Sentry AI | 2 | Minor | 1 empty bullet |
| 61 | diststream/Kafka internals course | 2 | OK | — |
| 62 | diststream/Kafka Streams and Rebalancing | 12 | Layout | 5 nested items flattened |
| 63 | main/Grocery | 19 | Layout | 9 checkboxes lose their checked/unchecked state |
| 64 | cucina/Branzino al forno | 5 | OK | — |
| 65 | DBstorage/TigerBeetle | 9 | Layout | 2 nested items flattened |
| 66 | plans and reflections/Evernote_index | 12 | Minor | 12 dead links to other notes |
| 67 | main/Load test investigation | 11 | Layout | 1 nested items flattened |
| 68 | system design/https15721.courses.cs.cmu.eduspring2016pape… | 1 | OK | — |
| 69 | system design/httpsnumenta.com | 1 | OK | — |
| 70 | healthcare/Crossover lab tests | 4 | Minor | `Untitled Attachment` caption shown as text |
| 71 | AI/ML Infra requirements | 22 | Layout | 11 nested items flattened |
| 72 | DBstorage/DynamoDB | 33 | Layout | 6 nested items flattened |
| 73 | diststream/httpswww.youtube.comwatchv=08AjVGGQaKQ | 2 | OK | — |
| 74 | immigration/Naturalization test material | 5 | OK | — |
| 75 | AI/Context Engineering practices | 24 | Layout | 7 nested items flattened |
| 76 | ISF/Evernote_index | 8 | Minor | 8 dead links to other notes |
| 77 | main/Take Your Networking to the Next Level Build Actual … | 2 | OK | — |
| 78 | architecture/Rust web | 9 | OK | — |
| 79 | diststream/Sharding | 18 | Layout | 4 nested items flattened; 1 empty bullet |
| 80 | languages/exceptional C++ | 1 | OK | — |
| 81 | architecture/FB Papers | 14 | OK | — |
| 82 | main/httpsjepsen.ioanalysesetcd-3.4.3 | 1 | OK | — |
| 83 | Investments/Finances Plan 2026 | 25 | Layout | 2 nested items flattened; 1 empty bullet |
| 84 | real estate/Avalon 255 King | 63 | Layout | 13 nested items flattened; 2 empty bullets |
| 85 | main/Clickhouse test | 7 | OK | — |
| 86 | main/5 effective networking strategies in the digital age… | 1 | OK | — |
| 87 | cucina/jus | 10 | OK | — |
| 88 | architecture/httpswww.honeycomb.ioblogsecondary-storage-t… | 1 | OK | — |
| 89 | diststream/Gossip protocols | 15 | OK | — |
| 90 | AI/Labeling with LLM | 5 | Layout | 2 nested items flattened |
| 91 | Trips/Hotels | 63 | Layout | 1 nested items flattened; `Untitled Attachment` caption shown as text |
| 92 | system design/Reverse Proxies | 74 | Layout | 44 nested items flattened |
| 93 | cucina/Prime rib (1) | 16 | Minor | 1 empty bullet |
| 94 | Investments/Managed portfolios options (not separate) | 26 | Layout | 19 nested items flattened; 1 bold section headers become plain text |
| 95 | AI/Notes on principles and arch | 13 | Layout | 1 lines lose bold/inline code |

No text was lost in any of the 95 sampled notes. Glued words (#42, #55) keep the text but
merge words together, which hurts search.

## Findings, by severity

### 1. Missing content: text next to a non-inline tag is dropped (bug)

When a block element has any child tag outside `_INLINE_TAGS`, `_process_node` recurses
into child *tags* only. The element's own text nodes are thrown away. The common trigger
is the legacy Evernote checkbox `<div class="para"><input class="en-todo"/>Text</div>`:
`input` is not in `_INLINE_TAGS`, so `Text` disappears.

- `Investments/Fidelity account`, `ISF/isf backup todo`, `recr/Recruit strategy`,
  `ISF/GDPR map`: **100% of the body text is lost**. Each imports as an empty note.
- `recr/Leaving FB` loses 146 of 190 words. `bureaucracy/Citizenship notes`,
  `Tokyo/Insurance stuff`, `main/Weekend (1)/(2)` and `ISF/ISF today` also lose text.
- 9 notes use this checkbox form. None of them came up in the random sample.

Fix: add `input` to the inline set (and render it as `[ ]`/`[x]`). Also never drop
`NavigableString` children when splitting a node into blocks.

### 2. Missing content: the 36% of notes that are web clips (by design, but large)

Per the spec, any note with `source=web.clip` is skipped. That is 506 notes, the largest
"missing content" item by far. Several notebooks are mostly clips. This is intended, but
it should be a deliberate product decision, not a side effect.

### 3. Layout: nested lists are flattened (known TODO, high impact)

This affects **41% of imported notes (366/886)** and 39 of the 95 sampled notes (284 items flattened in round 2 alone). Evernote
writes nested lists as a `<ul>` that is a *sibling* of the `<li>`, not a child. The
importer's `find_all("li")` turns every level into a top-level `- ` item. In outline-style
notes (recipes, trip plans, interview tracking) this loses the parent/child meaning, as in
notes 8, 14, 18 and 20. The block model would need an indent level (the editor now has
indent/unindent, #53).

### 4. Layout: words glued together in multi-paragraph list items (bug)

`_li_text` joins the rendered children of an `<li>` with `""`. When an item holds several
`div.para` (or a nested `<div>`), the words run together. Examples:
`"…what the insurance would pay for a procedureNot a problem in network"` and
`"Parameter passing experimentsdifferent types of constructors…"`. This affects 8 notes
(`Investments/Health insurance`, `languages/C++ todo`, `cucina/Agnello`, …).

### 5. Layout: all inline formatting is dropped

Bold, italic, strikethrough and inline code are all stripped. Only links survive. Bold is
how this export marks section headers (`<div class="para"><b>Breakfast</b></div>`), so the
document's structure is lost, not just its styling (notes 8 and 20). This affects 79
notes (9%) with bold/italic and 10 with inline code. Emitting `**…**`, `*…*`, `` `…` ``
and `~~…~~` would fix it, and would match how the markdown editor stores formatting.

### 6. Layout: check state of to-do lists is lost

28 notes use `ul.en-todolist` with `li[data-checked=true|false]`. They import as plain
`- ` bullets, so the checked/unchecked state is gone. The 9 legacy-checkbox notes in
finding 1 have the same problem, on top of losing their text.

### 7. Minor

- **Empty bullets:** 146 notes (16%) get a `- ` block with no text, because Evernote
  leaves an empty trailing `<li>`. Evernote shows these as blank bullets too, but they
  add noise.
- **Attachment captions leak into the text:** in 54 notes the attachment card's label
  (e.g. `Untitled Attachment`, or the file name) becomes a paragraph. Out of scope, but a
  placeholder would be cleaner, like the one already used for `<img>`. It should match
  `[data-resource-hash]`.
- **Dead note links:** internal links (`href="other note.html"`) are imported as they
  are and go nowhere (e.g. `AI/Evernote_index`).
- **Ordered lists (24 notes):** numbering restarts per `<ol>`, but nested `<ol>`s are
  numbered continuously with their parent, because of the flattening in finding 3. In
  `recr/HTTP server` (#44), three top-level steps, each with sub-steps, become one list
  numbered 1–13.
- **Tables (2 notes)** and **sub-headings h2–h6 (10 notes)** are rare. The table
  placeholder drops all of `Investments/401k rules` (267 words).

## Recommended order of fixes

1. Keep text next to `<input>`/unknown tags; render checkboxes (findings 1 and 6). This is
   a small parser change that stops whole notes from being silently emptied.
2. Join multi-paragraph `<li>` content with a space or newline (finding 4).
3. Inline formatting → Markdown (finding 5).
4. Nested list depth (finding 3): the biggest layout gap, but it needs block-model support.
5. Drop empty `<li>`s and attachment captions (finding 7).
6. Decide on web clips (finding 2).

## Re-running the evaluation

`scripts/eval_html_import.py` reproduces the results. It needs a local export, so it is not
part of `make check`.

```bash
python scripts/eval_html_import.py ~/Documents/notes                  # all imported notes
python scripts/eval_html_import.py ~/Documents/notes --sample 95 -v   # random sample, with diffs
python scripts/eval_html_import.py ~/Documents/notes --only-web-clips # web clips only
```

The script renders the HTML and the importer's Markdown through the same independent
reference walker, and compares the two line by line. For the Markdown, it converts each
payload with markdown-it, the same per-node parse the editor does. Each difference is
classified as nesting, numbering, checkbox, formatting, wrong block type, empty bullet,
or missing/extra line. A word-level check reports words in the HTML that are missing from
the import. Links are compared by text only. Attachments are compared as placeholders.
