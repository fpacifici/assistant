## Mobile-friendly web UI

The web UI today assumes a desktop-sized window: a fixed 300px sidebar
(notebook list + note list) next to the note editor, and a header carrying
the user name, invite link, quota and logout. On a phone none of this fits.

We want the same site to work on phones (~6.3" displays) and tablets, in
both portrait and landscape. This is **not** a native app — it is the same
React SPA, adapting its layout to the screen size.

## Requirements

- Every feature and login system available on desktop is available on
  mobile: password login, Google sign-in, registration, invites, email
  confirmation, notebook/note CRUD, sharing, editing, attachments, the debug
  block view.
- The layout mode is chosen from the screen size. There is no separate
  mobile URL.
- A URL override forces a layout mode on any device, so the mobile layout
  can be exercised from a desktop browser.
- Both layouts are covered by unit tests (Vitest + jsdom).

## Layout mode

Two modes: `desktop` and `mobile`.

- **mobile** when the viewport width is `< 768px` **or** its height is
  `< 500px`. A phone is therefore mobile in both orientations (landscape
  phones are ~850–930px wide but ~390px tall), and rotating a phone never
  flips the mode.
- **desktop** otherwise. Tablets (≥ 768px wide, ≥ 500px tall in both
  orientations) get the desktop layout. Below 1024px width the desktop
  sidebar narrows (~240px) to leave room for the editor.
- **Override**: `?layout=mobile` or `?layout=desktop` on any URL forces the
  mode and persists it for the browser tab (session storage), surviving
  navigation and the login redirect. `?layout=auto` clears the override.

The mode is decided in JavaScript and exposed to components; CSS media
queries handle sizing, spacing and touch targets only. Structural decisions
(which panels render) must not depend on CSS alone, so they are testable in
jsdom.

## Mobile navigation

The three views — notebook selection, note selection, note editing — are
shown one at a time, full screen. No new routes: the existing URL hierarchy
decides the view, and the deepest level wins.

| URL | Mobile view | Back goes to |
|---|---|---|
| `/notebooks` | Notebook list | — |
| `/notebooks/:notebookId/notes` | Note list of that notebook | `/notebooks` |
| `/notebooks/:notebookId/notes/:noteId` | Note editor | `/notebooks/:notebookId/notes` |

Browser back / swipe-back work naturally because each view is a history
entry.

Mobile top bar: **[← back] [title] [⋯]**. The title is "Notebooks", the
notebook name, or the note title. The `⋯` menu holds the user name, the
invite quota, the Invites link (when invites are enabled) and Logout, plus
view-specific actions (see editor).

Switching mode while a note is open (desktop window resize, override) must
not discard unsaved edits: the editor keeps its React identity across modes.

## Mobile editor

- The formatting toolbar is a single horizontally scrolling row, sticky at
  the top of the editor.
- **Save** lives in the top bar; the save status (Saved / Error / Conflict)
  is a thin line under the top bar.
- **Share** and **Debug** are entries in the `⋯` menu. The debug block view
  opens full screen.
- Attachments stay below the note body.
- Desktop keeps its current editor chrome (bottom Save/Debug/Share bar).

## Lists, dialogs and standalone pages

- Notebook/note row actions (share, delete) stay inline, with ≥ 44px touch
  targets on mobile. The create forms stay inline.
- Deleting a notebook or note asks for confirmation — on **both** layouts.
- The share dialog (and other modals) is full screen on mobile.
- Login, Register, Accept invite, Confirm email: responsive CSS only (fluid
  width, 16px inputs to avoid iOS zoom, touch-sized buttons). Google sign-in
  stays a full-page redirect.
- The Invites page uses the mobile top bar with back to `/notebooks`.

## Unsaved changes

Leaving the note editor with unsaved changes asks "Discard unsaved
changes?" — on both layouts, and for every navigation path: in-app links,
the mobile back arrow, browser back, swipe-back. Closing or reloading the
tab triggers the browser's native `beforeunload` prompt.

## Viewport correctness

- Use dynamic viewport units (`100dvh`, with `100vh` fallback) so browser
  chrome on mobile doesn't clip the layout.
- Respect safe-area insets (`viewport-fit=cover` + `env(safe-area-inset-*)`)
  for notched devices.

## Testing

Vitest + React Testing Library in jsdom:

- Layout mode detection: each threshold, orientation change, override
  set/persist/clear.
- `Layout` tests run in both modes, asserting which panels and header
  elements render at each URL level.
- Mode switch mid-edit preserves unsaved editor content.
- Delete confirmation and the unsaved-changes guard.
- A test helper renders any component in a forced mode.

Real-browser tests (Playwright) at device sizes are out of scope, tracked in
issue #49.

## Out of scope

- PWA manifest / add-to-home-screen / offline.
- A separate tablet (three-tier) layout.
- Gesture-based actions (swipe to delete, long-press menus).
- Autosave.
