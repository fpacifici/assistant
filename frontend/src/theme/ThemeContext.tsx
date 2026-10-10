/** Provides the color theme and the user's preference to the tree. */

import { createContext, useCallback, useContext, useLayoutEffect, useMemo, useState, useSyncExternalStore } from 'react';
import { colorSchemeOf, DARK_MEDIA_QUERY, readPreference, resolveTheme, writePreference } from './theme';
import type { ColorScheme, Theme, ThemePreference } from './theme';

interface ThemeContextValue {
  /** The applied theme. */
  theme: Theme;
  /** The light/dark base of the applied theme (for components with only two modes). */
  colorScheme: ColorScheme;
  /** What the user chose; `'system'` follows the OS setting. */
  preference: ThemePreference;
  setPreference: (preference: ThemePreference) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: 'light',
  colorScheme: 'light',
  preference: 'system',
  setPreference: () => {},
});

function subscribeToColorScheme(onChange: () => void): () => void {
  if (typeof window.matchMedia !== 'function') return () => {};
  const mql = window.matchMedia(DARK_MEDIA_QUERY);
  mql.addEventListener('change', onChange);
  return () => mql.removeEventListener('change', onChange);
}

function systemIsDark(): boolean {
  if (typeof window.matchMedia !== 'function') return false;
  return window.matchMedia(DARK_MEDIA_QUERY).matches;
}

function localStorageOrNull(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/**
 * Resolve the theme from the stored preference (`localStorage`) and the OS
 * color scheme, and mirror it on `<html data-theme="…">` for CSS. The inline
 * script in `index.html` applies the same rule before first paint.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() =>
    readPreference(localStorageOrNull()),
  );
  const systemDark = useSyncExternalStore(subscribeToColorScheme, systemIsDark);
  const theme = resolveTheme(preference, systemDark);

  useLayoutEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const setPreference = useCallback((next: ThemePreference) => {
    writePreference(localStorageOrNull(), next);
    setPreferenceState(next);
  }, []);

  const value = useMemo(
    () => ({ theme, colorScheme: colorSchemeOf(theme), preference, setPreference }),
    [theme, preference, setPreference],
  );
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
