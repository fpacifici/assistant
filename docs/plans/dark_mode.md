# Dark mode (web + mobile)

## Goal

Offer a dark theme across the whole SPA, in both the desktop and the mobile
layout, including auth pages, dialogs, the debug panel and the BlockNote
editor.

## Design

- Preference `system | light | dark`, default `system` (follows the OS),
  persisted per browser in `localStorage`. No backend changes: the
  preference is a device setting, like the layout override.
- Theme applied as `<html data-theme>`; an inline script in `index.html`
  sets it before first paint to avoid a light flash.
- All colors in `index.css` become CSS variables with a light set on `:root`
  and a dark set under `[data-theme="dark"]`.
- The app header / mobile top bar stays dark in both themes.
- Switcher: a select in the desktop header; radio items in the mobile `⋯`
  menu.
- BlockNote gets `theme={theme}`, with its editor background and text mapped
  to the app tokens.

## Steps

1. `theme/theme.ts` (pure rules) and `theme/ThemeContext.tsx` (provider + hook).
2. Mount `ThemeProvider` in `RootProviders` and `renderWithProviders`.
3. Tokenize `index.css` and add the dark token set.
4. `ThemeSwitcher` in `DesktopHeader` and `OverflowMenu`; pass the theme to
   `BlockNoteView`.
5. Pre-paint script plus `color-scheme` / `theme-color` metas in `index.html`.
6. Tests: pure rules, provider (OS changes, persistence), mobile menu.
7. Document in `docs/architecture/frontend.md`.

## Possible follow-ups

- Sync the preference to the user profile so it follows the user across
  devices.
- Make `theme-color` follow an explicit preference (it currently follows
  the OS scheme only).
