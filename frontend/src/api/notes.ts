import { apiFetch } from './client';
import type { Note } from '../types';

export function fetchNotes(notebookId: string): Promise<Note[]> {
  return apiFetch<Note[]>(`/notebook/${notebookId}/note`);
}

export function createNote(notebookId: string, title: string): Promise<Note> {
  return apiFetch<Note>(`/notebook/${notebookId}/note`, {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export function deleteNote(notebookId: string, noteId: string): Promise<void> {
  return apiFetch<void>(`/notebook/${notebookId}/note/${noteId}`, {
    method: 'DELETE',
  });
}
