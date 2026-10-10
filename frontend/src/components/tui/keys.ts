/**
 * Keyboard map of the TUI layout (Midnight Commander style), as pure
 * functions so it can be tested without a DOM.
 *
 * Function keys F1–F10 run the commands on the bottom key bar. Browsers and
 * laptops often swallow F-keys, so Alt+1 … Alt+0 and Esc followed by a
 * digit (as in mc) are equivalents.
 */

export type Pane = 'notebooks' | 'notes' | 'editor';
export type ListPane = Exclude<Pane, 'editor'>;

/** A command the controller sends to a list pane. */
export type ListCommand =
  | 'up'
  | 'down'
  | 'home'
  | 'end'
  | 'pageUp'
  | 'pageDown'
  | 'open'
  | 'new'
  | 'delete'
  | 'share'
  | 'filter'
  /** Share / delete the note open in the editor rather than the one under the cursor. */
  | 'shareOpen'
  | 'deleteOpen';

export type TuiAction =
  | { type: 'fkey'; n: number }
  | { type: 'list'; command: ListCommand }
  | { type: 'pane'; to: 'next' | 'prev' | 'left' | 'right' }
  | { type: 'escape' };

/** The subset of `KeyboardEvent` the key map reads. */
export interface KeyLike {
  key: string;
  code: string;
  altKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
}

/** Labels of the bottom key bar, F1 to F10. */
export const FKEY_LABELS: Record<number, string> = {
  1: 'Help',
  2: 'Share',
  3: 'Hide',
  4: 'Edit',
  5: 'Tags',
  6: 'Filter',
  7: 'New',
  8: 'Delete',
  9: 'Menu',
  10: 'Classic',
};

/** Time window for the digit after Esc to count as an F-key. */
export const ESC_DIGIT_WINDOW_MS = 1500;

/** F-key number for a `Digit1`…`Digit0` key code (0 is F10), else null. */
export function digitFkey(code: string): number | null {
  const match = /^Digit(\d)$/.exec(code);
  if (!match) return null;
  const digit = Number(match[1]);
  return digit === 0 ? 10 : digit;
}

const LIST_KEYS: Record<string, ListCommand> = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  Home: 'home',
  End: 'end',
  PageUp: 'pageUp',
  PageDown: 'pageDown',
  Enter: 'open',
};

/**
 * Map a key press to a TUI action, or null to let the browser handle it.
 *
 * While `typing` (focus in the editor or a text field) only F-keys, their
 * Alt+digit equivalents and Escape are taken, so text editing keeps
 * arrows, Tab and Enter.
 */
export function resolveKey(e: KeyLike, { typing }: { typing: boolean }): TuiAction | null {
  const fkey = /^F(\d{1,2})$/.exec(e.key);
  if (fkey && !e.altKey && !e.ctrlKey && !e.metaKey) {
    const n = Number(fkey[1]);
    return n >= 1 && n <= 10 ? { type: 'fkey', n } : null;
  }
  if (e.altKey && !e.ctrlKey && !e.metaKey) {
    const n = digitFkey(e.code);
    if (n !== null) return { type: 'fkey', n };
  }
  if (e.key === 'Escape') return { type: 'escape' };
  if (typing || e.altKey || e.ctrlKey || e.metaKey) return null;

  if (e.key === 'Tab') return { type: 'pane', to: e.shiftKey ? 'prev' : 'next' };
  if (e.key === 'ArrowLeft') return { type: 'pane', to: 'left' };
  if (e.key === 'ArrowRight') return { type: 'pane', to: 'right' };
  if (e.key === '?') return { type: 'fkey', n: 1 };
  const command = LIST_KEYS[e.key];
  return command ? { type: 'list', command } : null;
}

/** The pane Tab / Shift+Tab / ←/→ moves to among the `visible` panes. */
export function nextPane(
  current: Pane,
  to: 'next' | 'prev' | 'left' | 'right',
  visible: Pane[],
): Pane {
  if (visible.length === 0) return current;
  const index = visible.indexOf(current);
  if (index === -1) return visible[0];
  if (to === 'next') return visible[(index + 1) % visible.length];
  if (to === 'prev') return visible[(index - 1 + visible.length) % visible.length];
  if (to === 'left') return visible[Math.max(0, index - 1)];
  return visible[Math.min(visible.length - 1, index + 1)];
}
