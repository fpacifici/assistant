/** Pure color-theme rules: the stored preference and how it resolves. */

export type Theme = 'light' | 'dark';
export type ThemePreference = Theme | 'system';

export const THEME_PREFERENCES: readonly ThemePreference[] = ['system', 'light', 'dark'];

export const THEME_STORAGE_KEY = 'assistant.theme';
export const DARK_MEDIA_QUERY = '(prefers-color-scheme: dark)';

function isThemePreference(value: string | null): value is ThemePreference {
  return value === 'system' || value === 'light' || value === 'dark';
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
