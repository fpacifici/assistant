# Implementation plan: HTML import fixes

Fixes the issues found in [`docs/reports/html-import-evaluation.md`](../reports/html-import-evaluation.md)
when the HTML importer (PR #38) was run against the real Evernote export.
There is one step per issue. Dead links between notes are out of scope, because the
app has no links between notes yet.

## Context

The importer is `src/assistant/adapters/html_parser.py`: a pure function that turns
HTML into `ParsedBlock(block_type, payload)`. Each block becomes one server node. Two
facts from the frontend decide how several of these fixes work:

- **One node per *top-level* BlockNote block.** `reconcile.ts` iterates
  `editor.document`, which holds only the top-level blocks. It stores each one as
  `blocksToMarkdownLossy([block])`, and that call serialises the block's nested
  children into the **same payload** as indented Markdown. `mapper.ts` reverses this
  with `tryParseMarkdownToBlocks(payload)`, taking `parsed[0]` with its children.
  So a nested list is not a sequence of nodes. It is one `list_item` node per
  top-level item, with the whole subtree in that node's payload.
- **The node type is coarse.** `MarkdownBlockType` has `paragraph`, `heading`,
  `list_item`, `code_block`, `blockquote` and `image`. Bullet, numbered and check-list
  items all map to `list_item`, and tables map to `paragraph`. BlockNote rebuilds the
  real block type from the payload Markdown. For example, it reads `- [x] foo` as a
  `checkListItem`. So none of the steps below needs a schema change.

The frontend takes its snapshot (`buildSnapshot`) from the re-serialised blocks, not
from the raw payload. A payload that BlockNote normalises differently will therefore
not cause spurious PATCHes on the first save. A payload that BlockNote *cannot parse
into the intended structure* will still render wrong. Every step that introduces a new
Markdown form must pin that form with a frontend round-trip test (see "Shared test
approach").

## Shared test approach

- **Parser tests** (`tests/adapters/test_html_parser.py`) cover each issue with a
  small HTML snippet shaped like Evernote's markup:
  - lists are `ul[role=list]` with `li > div.list-content > div.para`;
  - a nested list is a `<ul>` that is a *sibling* of its parent `<li>`;
  - a checklist is `ul.en-todolist > li[data-checked]`;
  - an attachment is `div[data-resource-hash]`.

  Write the tests first (TDD), one `# --- <issue> ---` section per step. The fixtures
  are synthetic: never copy personal note content into the repo.
- **Frontend round-trip tests** (`frontend/src/markdown/mapper.test.ts`) apply to
  steps that add a new payload form (nested lists, checkboxes, inline formatting,
  tables). Each test asserts that `tryParseMarkdownToBlocks(payload)` gives the
  intended block tree, i.e. the right types, children, `checked` prop and styles.
  These tests are the contract between the importer and the editor.
- **Regression harness:** after each step, re-run the evaluation script from the
  report over the same 95 sampled notes, plus a word-level check over all 886
  notes. The issue's count must drop to 0 and nothing else may regress. The final
  step moves this script into the repo.

## Step 1 — Text next to non-inline tags is dropped (missing content)

**Problem.** In `_process_node`, if an element has any child tag outside
`_INLINE_TAGS`, the parser recurses into child *tags* only. The element's own text
nodes are lost. Evernote's older checkbox form,
`<div class="para"><input class="en-todo"/>Text</div>`, triggers this because `input`
is not inline. Four notes import empty and about 10 lose text.

**Change.**
- In the "has block child" branch, walk `el.children` in order, **including
  `NavigableString`s**. Collect runs of consecutive inline content (text and inline
  tags) into a buffer, and flush the buffer as a `paragraph` block whenever a block
  child appears and at the end. Block children still recurse as now. Mixed content
  then produces `paragraph(text before) / child blocks / paragraph(text after)`, and
  no text is lost.
- Add `input` to `_INLINE_TAGS` so an `en-todo` checkbox doesn't split its `div.para`
  into blocks. Step 4 turns it into a checklist item; until then it renders as nothing.
- Make the fallback rule explicit: any tag we don't recognise and that has no block
  children is treated as inline. This is spec rule 10: "everything not explicitly
  handled falls back to a plain paragraph".

**Tests.** A `div.para` with `<input>` followed by text keeps the text. Mixed text and
block children keep their order. A real 4-paragraph legacy checkbox note produces 4
blocks.

**Done when** the word-level check over all 886 notes reports 0 notes with missing
words. The only allowed exceptions are tables, which step 9 fixes.

## Step 2 — Words glued together in multi-paragraph list items

**Problem.** `_li_text` joins the rendered children with `""`. When an `<li>` holds
several `div.para` elements, or a `<div>` wrapping more text, adjacent words merge,
e.g. `procedureNot`, `experimentsdifferent`.

**Change.** While rendering an `<li>`'s inline content, treat every block-level
descendant boundary (`div`, `p` and anything else not in `_INLINE_TAGS`) as a
separator. Emit `" "` between blocks, the same way `<br>` is handled today, and let
`_normalize` collapse the whitespace. A list item stays a single block with one line
of inline content, because BlockNote list items have no multi-paragraph body.

**Tests.** `<li><div class="list-content"><div class="para">a</div><div class="para">b</div></div></li>`
gives `- a b`. A nested `<div>` inside a `para` also gets a separator.

**Done when** the 8 affected notes (e.g. `Health insurance`, `C++ todo`) show no
glued tokens in the word-level check.

## Step 3 — Inline formatting is dropped (including bold section headers)

**Problem.** `_render_inline` keeps only links. Bold, italic, strikethrough and inline
code are all lost. The export marks section headers as `<div class="para"><b>Header</b></div>`,
so dropping bold also drops the document's structure. This affects 79 notes.

**Change.**
- In `_render_inline`, wrap the output:
  - `b`/`strong` → `**…**`
  - `i`/`em` → `*…*`
  - `s`/`strike`/`del` → `~~…~~`
  - `code`, or a `span` carrying Evernote's inline-code class → `` `…` ``

  Don't emit a marker when the inner text is empty or whitespace-only. Move leading
  and trailing whitespace outside the markers (`**foo **` is not valid emphasis).
  Inside `code`, don't format nested tags or escape characters.
- **Escape literal Markdown in text nodes.** Once real markers are emitted, a plain
  `*`, `_`, `` ` ``, `[`, `]` or `~` in text, or a leading `#`, `-`, `+` or `1.`
  that only happens to look like Markdown, must not be read as Markdown. An example
  from the export is `A[Ix, J] * B[J, Ky]`. Add an `_escape_markdown(text)` helper
  for `NavigableString` output. Don't apply it inside `code` or to link URLs. This
  also fixes a latent bug: today a paragraph that starts with `# ` or `- ` already
  turns into a heading or list when the editor loads it.
- Bold-only paragraphs stay paragraphs whose payload is `**Header**`. Don't
  promote them to headings: that would guess at intent, and bold already renders as
  a visual header.
- The title `<h1>` keeps using plain text (`_inline_text` without markers), because
  note titles are not Markdown.

**Tests.** Each tag maps to the right marker. Nested `<b><i>x</i></b>` gives `***x***`.
Whitespace sits outside the markers. Empty `<b></b>` gives nothing. Literal `*` and a
leading `#` are escaped. Code content is not escaped. The frontend round-trip test
confirms that `**a** *b* ~~c~~ \`d\`` parses into the matching BlockNote styles, and
that escaped text renders literally.

**Done when** the 4 notes with lost bold headers and the 4 with other lost formatting
in the sample match the reference.

## Step 4 — Checklist state is lost

**Problem.** Lists with `ul.en-todolist > li[data-checked=true|false]` (28 notes), and
older `input.en-todo[checked]` paragraphs (9 notes), import as plain bullets or
paragraphs. Whether each item is checked is lost.

**Change.**
- In `_process_list`, if the `<ul>` has class `en-todolist`, give each direct `<li>`
  the prefix `- [x] ` or `- [ ] `, based on `data-checked == "true"`. Use
  `block_type="list_item"`, as BlockNote's `checkListItem` does. Nested plain `<ul>`s
  inside a todo list stay plain bullets. The export has `en-todolist` wrappers that
  contain only nested plain lists, and they must not turn into checkboxes.
- Ignore the `input.list-bullet-todo` that Evernote puts in *every* `<li>`. It is
  hidden by CSS unless the list is a todo list.
- Old format: a `div.para` whose first meaningful child is `input.en-todo` becomes
  `- [x] text` if the `checked` attribute equals `"true"`, and `- [ ] text`
  otherwise. Note that the attribute is present with the value `"false"` on
  unchecked items, so don't test whether it exists. Runs of these paragraphs
  become consecutive list items.

**Tests.** Checked and unchecked `en-todolist` items. A plain nested list under a
todo list. A plain list whose items have a hidden `list-bullet-todo` gives no
checkbox. Old-format `checked="false"` and `checked="true"`. The frontend round-trip
test confirms that `- [x] a` parses to `checkListItem` with `checked: true`.

**Done when** `main/Grocery` shows 7 checked and 2 unchecked items, and
`Investments/Fidelity account` imports as a checklist.

## Step 5 — Nested lists are flattened

**Problem.** `_process_list` uses `find_all("li")`, which flattens every level. Also,
Evernote nests a sub-list as a sibling `<ul>` of the `<li>` it belongs to, not inside
it. This affects 41% of notes.

**Change.**
- Replace the flat `find_all` with a recursive walk of the list's **direct
  children**:
  - an `<li>` starts a new item;
  - a `<ul>`/`<ol>` sibling attaches as children of the *previous* `<li>` (or of a
    synthetic empty parent if there is none);
  - a `<ul>`/`<ol>` inside an `<li>` attaches to that `<li>`.

  This builds an in-memory tree `ListItem(marker, text, children)`.
- Emit **one `ParsedBlock` per top-level item**. Its payload is the item line plus
  its subtree rendered as indented Markdown lines, joined with `\n`. This matches what
  the editor itself stores for a nested block (see Context). The indent unit must be
  whatever BlockNote's parser and `blocksToMarkdownLossy` agree on. First write the
  frontend round-trip test that fixes the format: parse a candidate payload and assert
  `children`. Then use that indent in the parser. Expected: children indented to the
  parent's content column, i.e. 2 spaces under `- `, 3 under `1. `, and 6 under
  `- [ ] `.
- Markers combine with steps 3 and 4: inline Markdown in the text, and the todo
  prefix at whatever level `en-todolist` applies.
- Ordered numbering is computed per list level (step 6).
- Remove the "nested list" TODO and update rule 6 of `docs/specs/adapters.md` so it
  says nesting is preserved.

**Tests.**
- A sibling-`<ul>` nested list gives one block with the child indented.
- Three levels deep.
- A nested list directly inside an `<li>`.
- A `<ul>` with a leading nested `<ul>` and no parent `<li>`.
- A bullet list inside a numbered list, and the reverse.
- Two top-level items each with children give 2 blocks.

The frontend round-trip test asserts that the nested payload parses into one block
with the correct `children` tree.

**Done when** `nested_flattened` is 0 across the 95-note sample. Also open
`cucina/Wellington` and `Trips/Vienna ristorante` after import, check the nesting in
the editor, and save once to confirm the payloads survive a save unchanged.

## Step 6 — Nested numbered lists are renumbered as one sequence

**Problem.** The `<ol>` counter runs over all descendant `<li>`s. Sub-steps therefore
continue the parent's numbering: `recr/HTTP server` is numbered 1–13 instead of
1–3, each with its own 1…n.

**Change.** Building on step 5's tree walk, each list gets its own counter that starts
at `int(ol["start"])` (default 1). The counter counts only that list's direct items.
Nested lists restart at their own start. Because each top-level item is a separate
node, the top-level numbering is written into each payload as `N. `. Confirm in the
round-trip test that BlockNote keeps consecutive `numberedListItem` blocks numbered
in sequence. If BlockNote renumbers adjacent blocks by itself, the written number
only has to be valid.

**Tests.** An `<ol>` with a nested `<ol>` gives a parent `1.`, `2.` and children
`1.`, `2.` under each. `start="5"` is respected. A bullet list nested in a numbered
list doesn't advance the numbered counter.

**Done when** `recr/HTTP server` matches the reference.

## Step 7 — Empty bullets

**Problem.** Evernote often leaves an empty trailing `<li>` (usually holding just a
`<br>`), which imports as a bare `- ` block. This affects 16% of notes.

**Change.** In the list walk, drop an item whose rendered text is empty *and* which
has no children. An empty item that *has* children is kept as an empty parent, so
the nesting survives. Because steps 1–2 drop no text, an item can only be empty if
it really has no content.

**Tests.** A trailing `<li><br></li>` emits nothing. A middle empty `<li>` emits
nothing. An empty `<li>` followed by a nested `<ul>` keeps the parent.

**Done when** `empty_bullet` is 0 across the sample.

## Step 8 — Attachment captions shown as text

**Problem.** Evernote shows an attachment as a `div[data-resource-hash]` card that
contains the file name, e.g. `Untitled Attachment`, and the name is imported as a
paragraph. Attachments are out of scope, but the card's caption shouldn't pass for
note content.

**Change.** In `_process_node`, treat any element with `data-resource-hash` (and
`en-media`) like `<img>`. Emit the existing placeholder style
`ParsedBlock("paragraph", "Skipped block: attachment")`, and don't descend into it.
`<img>` inside an attachment card produces nothing extra. Extend spec rule 9 in
`docs/specs/adapters.md` to cover attachments.

**Tests.** An attachment card gives exactly one placeholder and none of its inner text.
A note that is only a PDF gives a single placeholder.

**Done when** no imported note contains `Untitled Attachment`, and the 54 notes with
attachments show placeholders where the cards were.

## Step 9 — Tables are replaced by a placeholder

**Problem.** Tables currently become `Skipped block: table`, which threw away all of
`Investments/401k rules` (267 words). BlockNote supports tables, and the editor
already saves a table as a Markdown table in a `paragraph` node (`reconcile.ts` maps
unknown types to `paragraph`).

**Change.**
- Render `<table>` as a GFM pipe table in a single `paragraph` block:
  - the first row (or `<thead>` row) is the header;
  - add the `| --- |` separator row;
  - each cell is the cell's inline Markdown (step 3) with `|` escaped and line breaks
    turned into spaces;
  - pad short rows with empty cells so every row has as many cells as the widest one.
- Merged cells (`colspan`/`rowspan`) can't be expressed in GFM. Repeat the content
  into the extra cells for `colspan` and leave them empty for `rowspan`, so that no
  text is lost.
- A table nested inside a table cell is flattened to the text of its cells.
- Remove "table support" from the spec's out-of-scope list, and remove the TODO.

**Tests.** A simple 2×2 table with a header. `<thead>`/`<tbody>`. Ragged rows. `colspan`.
A `|` inside a cell. Inline formatting inside a cell. The frontend round-trip test
confirms that the pipe-table payload parses to a BlockNote `table` block with the
right cell count.

**Done when** `Investments/401k rules` keeps all its words, and both notes with tables
render as tables in the editor.

## Step 10 — Web clips are skipped (36% of notes)

**Problem.** Notes with `source=web.clip` are skipped entirely: 506 notes, the largest
amount of missing content. This is intended by user story 5 of the spec, so the fix
**changes the spec** and makes the behaviour configurable instead of removing it.

**Change.**
- Add an `--include-web-clips` CLI flag to `import_html_notes`. It defaults to off,
  so the spec's current behaviour stays the default. Thread it through
  `HTMLFileImportSource(root, include_web_clips=...)` →
  `parse_html_note(..., include_web_clips=...)`. When the flag is set, `skip` is
  never `True` and the clip is parsed like any other note.
- Web clips hold arbitrary site HTML: nested `div`s, `section`s, `pre`, `blockquote`,
  `figure`, inline styles. They exercise these parser paths, which personal notes
  never reach:
  - `<pre>` → `code_block`, with the payload as a fenced block holding the raw text;
  - `<blockquote>` → `blockquote`, with each line prefixed by `> `;
  - `<hr>` → nothing;
  - `<figure>`/`<picture>`/`<video>`/`<iframe>` → the attachment placeholder.

  Add these to `_process_node` as part of this step. Today `pre` falls through to a
  paragraph, which drops line breaks.
- Update user story 5 and the import rules in `docs/specs/adapters.md`, and
  `ImportStats` (web clips imported vs skipped).

**Tests.** With the flag off, current behaviour is unchanged. With it on, a web-clip
fixture imports. Add parser tests for `pre`, `blockquote` and `hr`. Add a CLI test
that the flag is forwarded.

**Done when** a run with `--include-web-clips` over the export imports all 1392 notes
with no errors. Then run a 20-note random sample of clips through the harness and
record the results in the evaluation report.

## Step 11 — Keep the evaluation harness

Not an issue, but needed to know the fixes worked and stay working. Move the
evaluation script into `scripts/eval_html_import.py`. Given an export directory, it
runs `HTMLFileImportSource`, builds the reference rendering and prints the issue
counts and the word-level missing-content check. Document it at the end of the
evaluation report. It needs a local export, so it is not part of `make check`.
Re-run it after the final step, and update `docs/reports/html-import-evaluation.md`
with before/after numbers.

## Build order and dependencies

Steps 1→2→3 come first, because they change how inline content is rendered and every
later step builds on that. Step 4 depends on step 1 (`input` handling) and step 3
(inline output). Step 5 depends on step 4 (nested todo markers). Steps 6 and 7 both
use step 5's list tree. Steps 8 and 9 are independent and can be done at any point
after step 3. Step 10 comes last, because it depends on all the block types being
correct. Each step is its own commit, and `make check` passes after each one.
Frontend round-trip tests need `make frontend-test`.

## Verification

- `make check` and `make frontend-test` pass after every step.
- The harness over the 95-sampled notes gives 0 for every issue except dead links.
- The word-level check over all 886 notes reports no missing words.
- Manual check:
  - import a handful of affected notes into a local DB (`make services-up`, then
    the CLI) and open them in the editor (`make dev`);
  - confirm nesting, checkboxes, bold headers and tables render correctly;
  - save once without editing, and confirm no node gets PATCHed. If one does, the
    payload format differs from what BlockNote re-serialises.
