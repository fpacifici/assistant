# Implementation plan: Mobile-friendly web UI

Implements `docs/specs/0006-mobile-layout.md`, per the decisions reached in
the `/grill-me` session on that spec.

## Context

The frontend (`frontend/src/`) is a React 19 SPA with React Router v7
(declarative `<BrowserRouter>` in `main.tsx`, nested `<Routes>` in
`App.tsx`), TanStack Query and BlockNote. All three note views render the
same `components/Layout.tsx`, which shows a fixed 300px `.sidebar`
(`NotebookList`, plus `NoteList` once a notebook is selected) and a `.main`
area (`NoteEditor` or a placeholder). The header shows title, Invites link,
quota badge, user name and Logout.

There are no media queries anywhere in `index.css`, `.app-shell` uses
`height: 100vh`, row actions are ~14px buttons, and delete has no
confirmation. `NoteEditor` owns all save state (`isDirty`, `saving`,
`status`) and renders its own bottom bar (Save / Debug / Share). There is
no navigation guard for unsaved edits on any layout.

Tests use `test/renderWithProviders.tsx`, which wraps in `MemoryRouter` +
`QueryClientProvider`. jsdom has no real viewport and does not evaluate
media queries, so layout decisions must live in JS to be unit-testable.

## Decisions recap (from grilling)

- **Hybrid mode detection**: a JS `LayoutMode` (`'mobile' | 'desktop'`)
  drives structure; CSS media queries drive sizing only.
- **Breakpoint**: mobile iff `width < 768 || height < 500`. Phones are
  mobile in both orientations; tablets are desktop. Desktop sidebar narrows
  to ~240px under 1024px.
- **Override**: `?layout=mobile|desktop|auto`, persisted in
  `sessionStorage`.
- **Navigation**: no new routes; on mobile the deepest URL level is the
  only view shown. Top bar `[← back] [title] [⋯]`.
- **Single `Layout` tree**: mode switches must not remount `NoteEditor`.
- **Editor chrome on mobile**: scrolling sticky toolbar; Save in top bar via
  a portal slot; Share + Debug in `⋯` menu; Debug full screen.
- **Lists**: inline actions with 44px targets; delete confirmation on both
  layouts.
- **Dialogs**: full screen on mobile.
- **Auth pages**: CSS only.
- **Unsaved-changes guard**: migrate to a data router and use `useBlocker`,
  on both layouts, plus `beforeunload`.
- **Viewport fixes**: `100dvh`, safe-area insets.
- **Tests**: jsdom unit tests only; Playwright is a follow-up.
- **Delivery**: one PR, one commit per build step below. No GitHub issue.

## Build order (one commit each)

### Commit 1 — Migrate to a data router (no behavior change)

`useBlocker` only works under a data router, so do the migration first,
isolated, so any regression is attributable.

- `src/routes.tsx` (new): export a `routes: RouteObject[]` array mirroring
  today's routing exactly:
  - `/login`, `/register`, `/invite/:inviteId`, `/confirm-email/:token`
    — public.
  - A pathless layout route whose element is `<AuthProvider><Outlet /></AuthProvider>`
    (replaces `ProtectedRoutes`), with children: index `/` →
    `<Navigate to="/notebooks" replace />`, `/notebooks`,
    `/notebooks/:notebookId/notes`, `/notebooks/:notebookId/notes/:noteId`
    (all `<Layout />`), `/invites`.
  - A root route (pathless, `element: <RootProviders />` rendering
    `<Outlet />`) wrapping everything — the future home of
    `LayoutModeProvider` (commit 2). For now it just renders `<Outlet />`.
- `src/main.tsx`: `createBrowserRouter(routes)` + `<RouterProvider>` in
  place of `<BrowserRouter><App /></BrowserRouter>`.
- `src/App.tsx`: delete (its content moves into `routes.tsx`), or keep as a
  thin re-export if anything imports it — check with grep.
- **Important — keep `Layout` shared across the three note routes.** With
  three sibling routes each rendering `<Layout />`, React Router keeps the
  same element type at the same position, so `Layout` (and `NoteEditor`)
  are reused across URL changes as they are today. Verify this is still the
  case after migration; if not, restructure as one parent route
  `notebooks` with element `<Layout />` and optional child segments so the
  instance is shared.
- `src/test/renderWithProviders.tsx`: switch to `createMemoryRouter` +
  `<RouterProvider>`. Keep the signature (`ui`, `initialEntries`,
  `queryClient`); the `ui` becomes the element of a catch-all route so
  existing tests that pass `<Routes>…</Routes>` keep working. Where
  existing tests pass their own `<Routes>`, prefer migrating them to pass a
  `routes` option (new) instead of nesting `<Routes>` — do whichever keeps
  the diff smallest while all tests pass.
- Tests: the full existing suite must pass unchanged in assertions. Add
  one `routes.test.tsx` smoke test: `/` redirects to `/notebooks`; an
  unauthenticated protected route still triggers the login redirect
  (mock `getMe` to reject, assert `window.location.href` set to `/login`).

### Commit 2 — Layout mode detection, override and test helper

- `src/layout/layoutMode.ts` (new, pure functions, no React):
  - `type LayoutMode = 'mobile' | 'desktop'`,
    `type LayoutOverride = LayoutMode | null`.
  - `MOBILE_MAX_WIDTH = 767`, `MOBILE_MAX_HEIGHT = 499`,
    `MOBILE_MEDIA_QUERY = '(max-width: 767px), (max-height: 499px)'`.
  - `modeForViewport(width, height): LayoutMode`.
  - `readOverride(search: string, storage: Storage | null): LayoutOverride`
    — parses `layout=` from the query string; `mobile`/`desktop` writes to
    storage key `assistant.layoutMode`, `auto` removes it; with no param,
    returns the stored value. Storage access wrapped in try/catch (private
    mode).
- `src/layout/LayoutModeContext.tsx` (new):
  - `LayoutModeProvider({ forcedMode?, children })`. If `forcedMode` is set
    (tests), uses it verbatim. Otherwise resolves the override from
    `useLocation().search` + `sessionStorage` (re-evaluated when `search`
    changes), and falls back to a `window.matchMedia(MOBILE_MEDIA_QUERY)`
    subscription (`useSyncExternalStore`, listening to `change`). Guard for
    `window.matchMedia` being undefined (default `desktop`).
  - `useLayoutMode(): LayoutMode` and `useIsMobile(): boolean`.
  - Also sets `data-layout="mobile|desktop"` on `document.documentElement`
    so CSS can key off the resolved mode (necessary for the override to
    affect styling, not just structure).
- Mount `LayoutModeProvider` in the root route element (`RootProviders`)
  so it covers public pages too.
- `src/test/matchMedia.ts` (new): `mockViewport(width, height)` installs a
  fake `window.matchMedia` that evaluates `MOBILE_MEDIA_QUERY` against the
  given size and exposes `resizeViewport(width, height)` which fires
  `change` listeners.
- `src/test/renderWithProviders.tsx`: add option
  `layout?: LayoutMode` → wraps in `LayoutModeProvider forcedMode={layout}`;
  default `'desktop'` so existing tests keep their meaning.
- Tests (`layoutMode.test.ts`, `LayoutModeContext.test.tsx`):
  - `modeForViewport`: 390×844 → mobile; 844×390 → mobile; 932×430 →
    mobile; 767×1024 → mobile; 768×1024 → desktop; 1024×768 → desktop;
    1366×1024 → desktop; 1440×900 → desktop; 1200×480 → mobile.
  - Provider follows `mockViewport` and updates on `resizeViewport`
    (simulated rotation 390×844 ↔ 844×390 stays mobile; 1024×768 →
    700×768 flips to mobile).
  - Override: `?layout=mobile` on a desktop viewport → mobile, persists
    after navigating to a URL without the param; `?layout=auto` clears;
    unknown value ignored; storage throwing is tolerated.
  - `document.documentElement.dataset.layout` reflects the mode.

### Commit 3 — Mobile `Layout`, top bar, menu and viewport fixes

- `src/components/Layout.tsx`: one component tree for both modes, so
  `NoteEditor` keeps its position/identity:

  ```
  <div className="app-shell" data-layout={mode}>
    {mobile ? <MobileTopBar …/> : <DesktopHeader …/>}
    <div className="layout">
      {showSidebar && <div className="sidebar">…lists…</div>}
      <div className="main">{noteId ? <NoteEditor /> : placeholder}</div>
    </div>
  </div>
  ```

  Key rule: `.main` and its `NoteEditor` child are always rendered in the
  same slot; mobile only changes what `.sidebar` contains and whether
  `.main` is rendered. Concretely on mobile:
  - `/notebooks` → sidebar with `NotebookList` only; `.main` not rendered.
  - `/notebooks/:id/notes` → sidebar with `NoteList` only; `.main` not
    rendered.
  - `/notebooks/:id/notes/:noteId` → sidebar not rendered; `.main` with
    `NoteEditor`.
  Placeholders ("Select a note…") are desktop-only.
  Keep sidebar before main in both modes so toggling the sidebar does not
  shift `.main`'s identity — give `.main` an explicit `key="main"` and the
  sidebar `key="sidebar"` to make identity independent of sibling
  presence.
- `src/components/DesktopHeader.tsx` (new): today's header, extracted
  verbatim.
- `src/components/MobileTopBar.tsx` (new): props `title`, `backTo?`,
  children for the `⋯` menu extras. Renders back `Link` (aria-label
  "Back"), title (ellipsized), an empty actions slot
  `<div id="topbar-actions">` (commit 4), and `OverflowMenu`.
- `src/components/OverflowMenu.tsx` (new): button `aria-label="Menu"`,
  toggles a popover `role="menu"`; closes on outside click, Escape, and
  item activation. Contains user name, quota badge, Invites link (when
  enabled), Logout, then any extra items passed in (via a small
  `TopBarMenuContext` registry so `NoteEditor` can add Share/Debug in
  commit 4).
- Titles: "Notebooks"; notebook name from the `['notebooks']` query cache
  (reuse `fetchNotebooks` query, same key as `NotebookList`); note title
  from `['note', notebookId, noteId]` (same key/fn as `NoteEditor`, so no
  extra request). Fall back to "Notes" / "Note" while loading.
- `src/pages/InvitesPage.tsx`: on mobile render `MobileTopBar` with title
  "Invites", `backTo="/notebooks"`, and hide the inline "Back to
  notebooks" link.
- `index.html`: `viewport` meta gains `viewport-fit=cover`.
- `src/index.css`:
  - `.app-shell { height: 100vh; height: 100dvh; }`.
  - Top bar styles; `padding-top: env(safe-area-inset-top)` and
    left/right insets on the top bar and `.layout`;
    `padding-bottom: env(safe-area-inset-bottom)` on scroll containers.
  - `[data-layout="mobile"] .sidebar { width: 100%; border-right: 0; }`,
    `[data-layout="mobile"] .main { padding: 12px; }`.
  - `@media (max-width: 1023px) { [data-layout="desktop"] .sidebar { width: 240px; } }`.
- Tests (`Layout.test.tsx`, refactored):
  - Wrap existing cases in `describe.each(['desktop', 'mobile'])` where
    the expectation is shared; split where it differs.
  - Desktop: unchanged assertions (notebook list always; note list when
    notebook selected; editor + note list when note selected; header
    Invites link + quota).
  - Mobile: `/notebooks` → notebook list, no note list, no editor, no back
    button, title "Notebooks"; `/notebooks/nb-1/notes` → note list only,
    back link to `/notebooks`, title = notebook name; `/…/notes/note-1` →
    editor only, back link to `/notebooks/nb-1/notes`, title = note title.
  - Mobile: header name/quota/Logout not visible until `Menu` opened;
    opening shows them; Invites item only when enabled; Logout calls
    `logout`.
  - **Mode-switch preservation**: render at `/…/notes/note-1` with the
    real mode provider and `mockViewport(1440, 900)`, with `NoteEditor`
    mocked as a component holding local state (e.g. a counter/text input);
    change the state, `resizeViewport(390, 844)`, assert the state
    survived (same instance); resize back, assert again.
  - `OverflowMenu.test.tsx`: open/close on click, Escape, outside click.
  - `MobileTopBar.test.tsx`: back link href, title, no back when
    `backTo` absent.
  - `InvitesPage.test.tsx`: mobile renders top bar with back link.

### Commit 4 — Mobile editor chrome

- `src/components/TopBarSlot.tsx` (new): `TopBarActions` component that
  portals its children into `#topbar-actions` when present (mobile), and
  renders nothing otherwise. Use a ref-callback/state registration via
  context rather than `document.getElementById`, so it works in tests and
  under StrictMode double mount.
- `TopBarMenuContext` (from commit 3): `useTopBarMenuItems(items)` hook to
  register extra `⋯` entries while mounted.
- `src/components/NoteEditor.tsx`:
  - Read `useIsMobile()`.
  - Mobile: render `<TopBarActions>` with the Save button (same
    `disabled` rules, same `handleSave`); register menu items Share (when
    `canShare`) and Debug/Hide Debug; render the status as
    `<div className="editor-status" role="status">` directly under the top
    bar (top of the editor). Do not render the bottom `.editor-toolbar`.
  - Desktop: unchanged.
  - Debug on mobile: render `DebugBlockView` inside a full-screen overlay
    (`.fullscreen-panel`, with a Close button) instead of the side-by-side
    `.with-debug` split.
  - All state stays in `NoteEditor`; only the render location of the
    controls changes, so mode switch keeps dirty/status state.
- `src/index.css`:
  - `[data-layout="mobile"] .md-toolbar` (check the actual class name in
    `MarkdownToolbar.tsx`): `position: sticky; top: 0; overflow-x: auto;
    flex-wrap: nowrap; -webkit-overflow-scrolling: touch;` buttons
    `min-width/height: 44px`.
  - `.fullscreen-panel`: `position: fixed; inset: 0;` with safe-area
    padding, scrollable.
  - `.editor-status` styles.
- Tests (`NoteEditor.test.tsx`, add mobile cases; mock BlockNote as the
  existing tests do):
  - Mobile: Save button is rendered inside the top bar slot (render
    `NoteEditor` under `Layout` or a test harness providing the slot), not
    in `.editor-toolbar`; Save disabled until dirty; clicking it calls
    `executeSave`; status line shows "Saved" / "Conflict…".
  - Mobile: Share and Debug appear as menu items when `Menu` opened; Share
    only with `share_note` permission; Debug opens the full-screen panel,
    Close hides it.
  - Desktop: bottom toolbar unchanged (existing tests).
  - `MarkdownToolbar` behavior is unchanged; no new tests beyond a smoke
    check that it renders in mobile mode.

### Commit 5 — Lists, dialogs and auth pages

- `src/components/ConfirmDialog.tsx` (new): modal with message, Cancel and
  a destructive confirm button; `role="alertdialog"`, focus on Cancel,
  Escape cancels. Full screen on mobile via shared modal CSS.
- `NotebookList.tsx`, `NoteList.tsx`: delete button opens
  `ConfirmDialog` ("Delete notebook "<name>"? This cannot be undone." /
  same for notes) and only calls `deleteMutation.mutate` on confirm. Both
  layouts.
  - If the deleted note is the currently open one, keep today's behavior
    (check what `NoteList` does now and preserve it).
- Touch targets, CSS only: under `[data-layout="mobile"]`,
  `.notebook-item, .note-item` min-height 48px; `.share-btn, .delete-btn`
  min 44×44; `.create-form input, button` 44px high, inputs
  `font-size: 16px`.
- Modals: `[data-layout="mobile"] .modal { width: 100%; max-width: none;
  height: 100dvh; max-height: none; border-radius: 0; }` with safe-area
  padding; `.modal-overlay` aligns to stretch. Applies to `ShareDialog`
  and `ConfirmDialog`.
- Auth pages (`.auth-page`, `.auth-card`, `InvitesPage` tables): fluid
  width (`width: 100%; max-width: <current>`), 16px inputs, 44px buttons;
  InvitesPage tables collapse to stacked rows under
  `[data-layout="mobile"]`. Use `[data-layout]` rather than raw media
  queries so the override applies.
- Tests:
  - `NotebookList.test.tsx` / `NoteList.test.tsx`: clicking delete shows
    the confirmation; Cancel does not call the API; Confirm calls it.
    Update existing delete tests accordingly.
  - `ConfirmDialog.test.tsx`: Escape cancels, buttons wired.
  - `ShareDialog.test.tsx`: renders in mobile mode (smoke).
  - Auth pages: one mobile smoke test each for `LoginPage` and
    `RegisterPage` (render with `layout: 'mobile'`, Google button and
    form present) — the layout is CSS-only, so this is a regression guard
    that nothing is structurally hidden.

### Commit 6 — Unsaved-changes guard

- `src/hooks/useUnsavedChangesGuard.ts` (new): `useUnsavedChangesGuard(isDirty: boolean)`.
  - `useBlocker(({ currentLocation, nextLocation }) => isDirty &&
    currentLocation.pathname !== nextLocation.pathname)`.
  - When `blocker.state === 'blocked'`, render `ConfirmDialog` "Discard
    unsaved changes?" (Discard → `blocker.proceed()`, Keep editing →
    `blocker.reset()`). Return the dialog element for the caller to render.
  - `beforeunload` listener while `isDirty` (call `preventDefault()`;
    browsers show their own text).
- `NoteEditor.tsx`: `const guard = useUnsavedChangesGuard(isDirty);` and
  render `{guard}`. Covers both layouts: desktop note/notebook clicks,
  mobile back arrow, browser back, swipe-back (all are router navigations
  or popstate, which `useBlocker` intercepts).
- Saving clears `isDirty`, so navigation after save is unblocked.
- Logout: goes through `window.location.href`, which triggers
  `beforeunload` — acceptable (browser-native prompt).
- Tests (`useUnsavedChangesGuard.test.tsx` + `NoteEditor.test.tsx`), using
  `createMemoryRouter`:
  - Not dirty → navigation proceeds, no dialog.
  - Dirty → `router.navigate(-1)` and link click both show the dialog;
    Keep editing stays on the note; Discard navigates.
  - Dirty in mobile mode → tapping the top-bar back link shows the dialog.
  - Query-string-only change (e.g. `?layout=mobile`) is not blocked.
  - `beforeunload` handler registered only while dirty.

### Commit 7 — Docs

- `docs/architecture/frontend.md`: update routing (data router,
  `routes.tsx`, root/auth layout routes), provider hierarchy
  (`RouterProvider` → root route with `LayoutModeProvider` → `AuthProvider`
  layout route), add a "Responsive layout" section (mode rule, override,
  `data-layout`, single-tree rule, top bar slot/menu), the unsaved-changes
  guard, and bring the stale parts up to date (auth pages, `AuthContext`,
  invites, share dialog, attachments).
- `docs/architecture/README.md`: already claims "works on browser and
  mobile" — no change needed beyond linking the spec if useful.

(Docs can be folded into commit 6 if it keeps history cleaner; the plan
lists them separately for clarity.)

## Test plan summary

- `make frontend-check` and `make frontend-test` pass after **every**
  commit.
- New test utilities: `mockViewport` / `resizeViewport`
  (`src/test/matchMedia.ts`), `renderWithProviders(ui, { layout })`.
- Coverage targets: every `Layout` URL level × both modes; every
  threshold of the mode rule; override lifecycle; mode switch preserving
  editor state; mobile editor controls; delete confirmation; guard on
  link, back arrow and history back.

## Verification (manual, after the last commit)

- `make dev`, open `http://localhost:5173/notebooks?layout=mobile` on
  desktop: walk notebook → notes → editor → back; edit and try back
  (guard); Save from top bar; Share and Debug from the menu; delete with
  confirmation; logout; login with password and Google.
- Chrome DevTools device mode: iPhone 15 (393×852) portrait and landscape,
  iPad (820×1180) portrait and landscape; confirm no horizontal page
  scroll, toolbar scrolls, modals full screen on phone.
- Resize a desktop window across 768px with a dirty note: edits survive.
- `?layout=auto` returns to automatic detection.

## Risks and notes

- **Data router migration** is the riskiest step; it's isolated in commit
  1 with no behavior change. Watch for `Layout` remounting between note
  routes (would lose editor state on every note switch) — covered by the
  instance-sharing check in commit 1.
- **BlockNote on touch**: its side menu (drag handle / `+`) and floating
  formatting toolbar are hover/selection driven. We rely on our own
  `MarkdownToolbar` on mobile and leave BlockNote defaults as-is; if its
  floating UI misbehaves on touch, hide it under
  `[data-layout="mobile"]` rather than patching BlockNote.
- **Soft keyboard**: with Save in the top bar nothing important sits at the
  bottom; `100dvh` handles the resized viewport on iOS 16+/Chrome.
- **StrictMode double mount** affects portal/slot registration — test the
  slot under StrictMode.

## Out of scope

- Playwright / real-browser layout tests (follow-up: #49).
- PWA manifest, add-to-home-screen, offline.
- Three-tier tablet layout; gesture actions; autosave.
