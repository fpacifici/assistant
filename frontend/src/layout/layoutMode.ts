/** Pure layout-mode rules: viewport thresholds and the `?layout=` override. */

export type LayoutMode = 'mobile' | 'desktop';
export type LayoutOverride = LayoutMode | null;

export const MOBILE_MAX_WIDTH = 767;
export const MOBILE_MAX_HEIGHT = 499;
export const MOBILE_MEDIA_QUERY = `(max-width: ${MOBILE_MAX_WIDTH}px), (max-height: ${MOBILE_MAX_HEIGHT}px)`;

export const OVERRIDE_STORAGE_KEY = 'assistant.layoutMode';

/** Mobile iff the viewport is narrower than 768px or shorter than 500px. */
export function modeForViewport(width: number, height: number): LayoutMode {
  return width <= MOBILE_MAX_WIDTH || height <= MOBILE_MAX_HEIGHT ? 'mobile' : 'desktop';
}

function isLayoutMode(value: string | null): value is LayoutMode {
  return value === 'mobile' || value === 'desktop';
}

/**
 * Resolve the layout override from a query string and session storage.
 *
 * `?layout=mobile|desktop` stores and returns that mode, `?layout=auto`
 * clears it, and any other (or missing) value falls back to the stored one.
 * Storage failures (e.g. private browsing) are ignored.
 */
export function readOverride(search: string, storage: Storage | null): LayoutOverride {
  const param = new URLSearchParams(search).get('layout');
  try {
    if (isLayoutMode(param)) {
      storage?.setItem(OVERRIDE_STORAGE_KEY, param);
      return param;
    }
    if (param === 'auto') {
      storage?.removeItem(OVERRIDE_STORAGE_KEY);
      return null;
    }
    const stored = storage?.getItem(OVERRIDE_STORAGE_KEY) ?? null;
    return isLayoutMode(stored) ? stored : null;
  } catch {
    return isLayoutMode(param) ? param : null;
  }
}
