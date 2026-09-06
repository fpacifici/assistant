import { apiFetch } from './client';
import type { Entitlement, Notebook } from '../types';

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
