/**
 * Keyboard cursor for the TUI list panes. The cursor follows an item id (so
 * refetches don't move it) and starts on the item open in the URL.
 */

import { useCallback, useEffect, useState } from 'react';
import type { ListCommand } from './keys';

/** Rows moved by PageUp / PageDown. */
export const PAGE_STEP = 10;

type MoveCommand = Extract<ListCommand, 'up' | 'down' | 'home' | 'end' | 'pageUp' | 'pageDown'>;

export function isMoveCommand(command: ListCommand): command is MoveCommand {
  return ['up', 'down', 'home', 'end', 'pageUp', 'pageDown'].includes(command);
}

/** Index after `command` from `index` in a list of `length` items. */
export function moveIndex(index: number, command: MoveCommand, length: number): number {
  if (length === 0) return -1;
  const target = {
    up: index - 1,
    down: index + 1,
    home: 0,
    end: length - 1,
    pageUp: index - PAGE_STEP,
    pageDown: index + PAGE_STEP,
  }[command];
  return Math.min(length - 1, Math.max(0, target));
}

export interface ListCursor<T> {
  index: number;
  current: T | undefined;
  move: (command: MoveCommand) => void;
  select: (id: string) => void;
}

/**
 * Cursor over `items`. `onReachEnd` runs when the cursor lands on the last
 * item, to load the next page.
 */
export function useListCursor<T extends { id: string }>(
  items: T[],
  activeId: string | undefined,
  onReachEnd?: () => void,
): ListCursor<T> {
  const [cursorId, setCursorId] = useState<string | null>(activeId ?? null);

  useEffect(() => {
    if (activeId) setCursorId(activeId);
  }, [activeId]);

  const found = items.findIndex((item) => item.id === cursorId);
  const index = found !== -1 ? found : items.length > 0 ? 0 : -1;

  const move = useCallback(
    (command: MoveCommand) => {
      const next = moveIndex(index, command, items.length);
      if (next === -1) return;
      setCursorId(items[next].id);
      if (next === items.length - 1) onReachEnd?.();
    },
    [index, items, onReachEnd],
  );

  return { index, current: index >= 0 ? items[index] : undefined, move, select: setCursorId };
}
