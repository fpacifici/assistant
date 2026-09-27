/** Fake `window.matchMedia` driven by a simulated viewport size (jsdom has none). */

import { MOBILE_MEDIA_QUERY, modeForViewport } from '../layout/layoutMode';

type Listener = (event: MediaQueryListEvent) => void;

const viewport = { width: 1440, height: 900 };
const listeners = new Set<Listener>();

function evaluate(query: string): boolean {
  if (query !== MOBILE_MEDIA_QUERY) return false;
  return modeForViewport(viewport.width, viewport.height) === 'mobile';
}

/** Install a fake `window.matchMedia` for a viewport of the given size. */
export function mockViewport(width: number, height: number): void {
  viewport.width = width;
  viewport.height = height;
  listeners.clear();
  window.matchMedia = (query: string) =>
    ({
      media: query,
      get matches() {
        return evaluate(query);
      },
      onchange: null,
      addEventListener: (_type: string, listener: Listener) => listeners.add(listener),
      removeEventListener: (_type: string, listener: Listener) => listeners.delete(listener),
      addListener: (listener: Listener) => listeners.add(listener),
      removeListener: (listener: Listener) => listeners.delete(listener),
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

/** Change the simulated viewport and notify `change` listeners. */
export function resizeViewport(width: number, height: number): void {
  viewport.width = width;
  viewport.height = height;
  const event = { matches: evaluate(MOBILE_MEDIA_QUERY), media: MOBILE_MEDIA_QUERY };
  for (const listener of [...listeners]) {
    listener(event as MediaQueryListEvent);
  }
}
