import { apiFetch } from './client';
import type { Entitlement, Note } from '../types';

export function fetchNotes(notebookId: string): Promise<Note[]> {
  return apiFetch<Note[]>(`/notebook/${notebookId}/note`);
}

export function fetchNote(notebookId: string, noteId: string): Promise<Note> {
  return apiFetch<Note>(`/notebook/${notebookId}/note/${noteId}`);
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

export function fetchNoteEntitlements(
  notebookId: string,
  noteId: string,
): Promise<Entitlement[]> {
  return apiFetch<Entitlement[]>(`/notebook/${notebookId}/note/${noteId}/share`);
}

export function shareNote(
  notebookId: string,
  noteId: string,
  email: string,
  role: string,
): Promise<Entitlement> {
  return apiFetch<Entitlement>(`/notebook/${notebookId}/note/${noteId}/share`, {
    method: 'POST',
    body: JSON.stringify({ email, role }),
  });
}

export function revokeNoteEntitlement(
  notebookId: string,
  noteId: string,
  entitlementId: string,
): Promise<void> {
  return apiFetch<void>(`/notebook/${notebookId}/note/${noteId}/share/${entitlementId}`, {
    method: 'DELETE',
  });
}
