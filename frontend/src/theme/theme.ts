/** Pure color-theme rules: the stored preference and how it resolves. */

/** Whether a theme is built on a light or a dark base (drives `color-scheme` and BlockNote). */
export type ColorScheme = 'light' | 'dark';

/** Every theme the app can apply. `light` and `dark` are the neutral defaults. */
export const THEMES = ['light', 'dark', 'blossom', 'ocean', 'sand', 'twilight'] as const;
export type Theme = (typeof THEMES)[number];
export type ThemePreference = Theme | 'system';

export const THEME_PREFERENCES: readonly ThemePreference[] = ['system', ...THEMES];

const COLOR_SCHEMES: Record<Theme, ColorScheme> = {
  light: 'light',
  dark: 'dark',
  blossom: 'light',
  ocean: 'dark',
  sand: 'light',
  twilight: 'dark',
};

export const THEME_STORAGE_KEY = 'assistant.theme';
export const DARK_MEDIA_QUERY = '(prefers-color-scheme: dark)';

function isThemePreference(value: string | null): value is ThemePreference {
  return value === 'system' || (THEMES as readonly (string | null)[]).includes(value);
}

/** Read the stored preference; missing, invalid or unreadable means `'system'`. */
export function readPreference(storage: Storage | null): ThemePreference {
  try {
    const stored = storage?.getItem(THEME_STORAGE_KEY) ?? null;
    return isThemePreference(stored) ? stored : 'system';
  } catch {
    return 'system';
  }
}

/** Persist the preference. `'system'` clears the key. Storage failures are ignored. */
export function writePreference(storage: Storage | null, preference: ThemePreference): void {
  try {
    if (preference === 'system') storage?.removeItem(THEME_STORAGE_KEY);
    else storage?.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // e.g. private browsing: the choice still applies for this page load.
  }
}

/** An explicit preference wins; `'system'` follows the OS color scheme. */
export function resolveTheme(preference: ThemePreference, systemDark: boolean): Theme {
  if (preference === 'system') return systemDark ? 'dark' : 'light';
  return preference;
}

/** The light/dark base a theme is built on. */
export function colorSchemeOf(theme: Theme): ColorScheme {
  return COLOR_SCHEMES[theme];
}
