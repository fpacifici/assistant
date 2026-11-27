/** Tells the server this tab has a note open, and where its cursor is. */

import { useCallback, useEffect, useRef, useState } from 'react';
import { leaveNote, sendHeartbeat } from '../api/presence';
import type { PresenceCursor } from '../types';

/** The server forgets a tab after three missed beats (30 s). */
export const HEARTBEAT_MS = 10_000;
/** Cursor moves are sent at most this often. */
export const CURSOR_THROTTLE_MS = 1_000;

function newClientId(): string {
  return crypto.randomUUID();
}

/**
 * While `noteId` is set, beat every `HEARTBEAT_MS` as long as the page is
 * visible (and right away when it becomes visible again), with the cursor
 * from `getCursor`. Leaving the note, or the page, deletes the presence.
 *
 * Returns `cursorMoved`, which sends a beat with the new cursor, at most
 * once per `CURSOR_THROTTLE_MS`. Failures are ignored: the next beat retries.
 */
export function useNotePresence(
  notebookId: string | undefined,
  noteId: string | undefined,
  getCursor: () => PresenceCursor | null,
): { cursorMoved: () => void } {
  const [clientId] = useState(newClientId);
  const getCursorRef = useRef(getCursor);
  const beatRef = useRef<(() => void) | null>(null);
  const lastBeat = useRef(0);
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    getCursorRef.current = getCursor;
  });

  useEffect(() => {
    if (!notebookId || !noteId) return;

    const beat = () => {
      if (pending.current !== null) {
        clearTimeout(pending.current);
        pending.current = null;
      }
      lastBeat.current = Date.now();
      sendHeartbeat(notebookId, noteId, clientId, getCursorRef.current()).catch(() => {});
    };
    beatRef.current = beat;
    beat();

    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') beat();
    }, HEARTBEAT_MS);
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') beat();
    };
    const onPageHide = () => leaveNote(notebookId, noteId, clientId);
    document.addEventListener('visibilitychange', onVisibilityChange);
    window.addEventListener('pagehide', onPageHide);

    return () => {
      beatRef.current = null;
      clearInterval(interval);
      if (pending.current !== null) clearTimeout(pending.current);
      pending.current = null;
      document.removeEventListener('visibilitychange', onVisibilityChange);
      window.removeEventListener('pagehide', onPageHide);
      leaveNote(notebookId, noteId, clientId);
    };
  }, [notebookId, noteId, clientId]);

  const cursorMoved = useCallback(() => {
    const beat = beatRef.current;
    if (!beat || pending.current !== null) return;
    const wait = lastBeat.current + CURSOR_THROTTLE_MS - Date.now();
    if (wait <= 0) beat();
    else pending.current = setTimeout(beat, wait);
  }, []);

  return { cursorMoved };
}
