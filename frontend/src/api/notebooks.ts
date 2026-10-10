import { apiFetch } from './client';
import { PAGE_SIZE } from './pagination';
import type { Entitlement, Notebook } from '../types';

/** One page of the caller's notebooks, sorted by name. */
export function fetchNotebooks(offset = 0, limit = PAGE_SIZE): Promise<Notebook[]> {
  return apiFetch<Notebook[]>(`/notebook?offset=${offset}&limit=${limit}`);
}

export function fetchNotebook(notebookId: string): Promise<Notebook> {
  return apiFetch<Notebook>(`/notebook/${notebookId}`);
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

export function fetchNotebookEntitlements(notebookId: string): Promise<Entitlement[]> {
  return apiFetch<Entitlement[]>(`/notebook/${notebookId}/share`);
}

export function shareNotebook(
  notebookId: string,
  email: string,
  role: string,
): Promise<Entitlement> {
  return apiFetch<Entitlement>(`/notebook/${notebookId}/share`, {
    method: 'POST',
    body: JSON.stringify({ email, role }),
  });
}

export function revokeNotebookEntitlement(
  notebookId: string,
  entitlementId: string,
): Promise<void> {
  return apiFetch<void>(`/notebook/${notebookId}/share/${entitlementId}`, {
    method: 'DELETE',
  });
}
