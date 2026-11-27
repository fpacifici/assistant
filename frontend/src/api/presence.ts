/**
 * Presence and live updates of an open note, by polling (like the reading
 * list): the open note beats and polls `live`, the note list polls the
 * notebook's presence. See `docs/architecture/notesservice.md`.
 */

import { apiFetch, apiUrl } from './client';
import type { LiveNote, NotePresence, PresenceCursor } from '../types';

function presencePath(notebookId: string, noteId: string, clientId: string): string {
  return `/notebook/${notebookId}/note/${noteId}/presence/${clientId}`;
}

/** Tell the server this tab has the note open, and where its cursor is. */
export function sendHeartbeat(
  notebookId: string,
  noteId: string,
  clientId: string,
  cursor: PresenceCursor | null,
): Promise<void> {
  return apiFetch<void>(presencePath(notebookId, noteId, clientId), {
    method: 'PUT',
    body: JSON.stringify({ cursor }),
  });
}

/**
 * Forget this tab on the note. `keepalive` lets it finish while the page
 * unloads; failures are ignored, the presence expires on its own.
 */
export function leaveNote(notebookId: string, noteId: string, clientId: string): void {
  fetch(apiUrl(presencePath(notebookId, noteId, clientId)), {
    method: 'DELETE',
    credentials: 'include',
    keepalive: true,
  }).catch(() => {});
}

/** The note's revision, its nodes when it is not `since`, and who else is on it. */
export function fetchLiveNote(
  notebookId: string,
  noteId: string,
  since: string | null,
): Promise<LiveNote> {
  const query = since ? `?since=${encodeURIComponent(since)}` : '';
  return apiFetch<LiveNote>(`/notebook/${notebookId}/note/${noteId}/live${query}`);
}

/** Who else is on each note of the notebook. */
export function fetchNotebookPresence(notebookId: string): Promise<NotePresence[]> {
  return apiFetch<NotePresence[]>(`/notebook/${notebookId}/presence`);
}
