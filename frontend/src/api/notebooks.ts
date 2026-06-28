import { apiFetch } from './client';
import type { Notebook } from '../types';

export function fetchNotebooks(): Promise<Notebook[]> {
  return apiFetch<Notebook[]>('/notebook');
}

export function createNotebook(name: string): Promise<Notebook> {
  return apiFetch<Notebook>('/notebook', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function deleteNotebook(notebookId: string): Promise<void> {
  return apiFetch<void>(`/notebook/${notebookId}`, {
    method: 'DELETE',
  });
}
