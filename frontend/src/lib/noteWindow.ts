/** Opening a note in its own browser window (desktop). */

/** URL of the standalone note window route. */
export function noteWindowPath(notebookId: string, noteId: string): string {
  return `/notebooks/${notebookId}/notes/${noteId}/window`;
}

/**
 * Open a blank popup for `noteId`, to be pointed at the note once pending
 * edits are saved. Must be called synchronously from the click handler, or
 * the browser's popup blocker steps in. Reuses the window if this note is
 * already open in one. Returns null when the popup was blocked.
 */
export function openNoteWindow(noteId: string): Window | null {
  return window.open('', `note-${noteId}`, 'popup,width=900,height=800');
}
