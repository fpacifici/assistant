import { apiFetch } from './client';
import type { Notebook } from '../types';

export function fetchNotebooks(userId: string): Promise<Notebook[]> {
  return apiFetch<Notebook[]>('/notebook', { userId });
}

export function createNotebook(userId: string, name: string): Promise<Notebook> {
  return apiFetch<Notebook>('/notebook', {
    method: 'POST',
    body: JSON.stringify({ name }),
    userId,
  });
}

export function deleteNotebook(notebookId: string): Promise<void> {
  return apiFetch<void>(`/notebook/${notebookId}`, {
    method: 'DELETE',
  });
}
