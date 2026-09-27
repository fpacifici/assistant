/** Provides the resolved layout mode (mobile/desktop) to the component tree. */

import { createContext, useContext, useLayoutEffect, useMemo, useSyncExternalStore } from 'react';
import { useLocation } from 'react-router';
import { MOBILE_MEDIA_QUERY, readOverride } from './layoutMode';
import type { LayoutMode } from './layoutMode';

const LayoutModeContext = createContext<LayoutMode>('desktop');

function subscribeToViewport(onChange: () => void): () => void {
  if (typeof window.matchMedia !== 'function') return () => {};
  const mql = window.matchMedia(MOBILE_MEDIA_QUERY);
  mql.addEventListener('change', onChange);
  return () => mql.removeEventListener('change', onChange);
}

function viewportIsMobile(): boolean {
  if (typeof window.matchMedia !== 'function') return false;
  return window.matchMedia(MOBILE_MEDIA_QUERY).matches;
}

function sessionStorageOrNull(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function ModeValue({ mode, children }: { mode: LayoutMode; children: React.ReactNode }) {
  // Expose the mode to CSS so the override affects styling, not just structure.
  useLayoutEffect(() => {
    document.documentElement.dataset.layout = mode;
  }, [mode]);
  return <LayoutModeContext.Provider value={mode}>{children}</LayoutModeContext.Provider>;
}

function AutoLayoutModeProvider({ children }: { children: React.ReactNode }) {
  const { search } = useLocation();
  const override = useMemo(() => readOverride(search, sessionStorageOrNull()), [search]);
  const viewportMobile = useSyncExternalStore(subscribeToViewport, viewportIsMobile);
  const mode: LayoutMode = override ?? (viewportMobile ? 'mobile' : 'desktop');
  return <ModeValue mode={mode}>{children}</ModeValue>;
}

/**
 * Resolve the layout mode from the `?layout=` override (persisted in session
 * storage) or, failing that, the viewport size. `forcedMode` bypasses both
 * and is meant for tests. Must be rendered inside a router.
 */
export function LayoutModeProvider({
  forcedMode,
  children,
}: {
  forcedMode?: LayoutMode;
  children: React.ReactNode;
}) {
  if (forcedMode) return <ModeValue mode={forcedMode}>{children}</ModeValue>;
  return <AutoLayoutModeProvider>{children}</AutoLayoutModeProvider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useLayoutMode(): LayoutMode {
  return useContext(LayoutModeContext);
}

// eslint-disable-next-line react-refresh/only-export-components
export function useIsMobile(): boolean {
  return useLayoutMode() === 'mobile';
}
