import { apiFetch } from './client';
import type { NoteNode } from '../types';

export function fetchNodes(notebookId: string, noteId: string): Promise<NoteNode[]> {
  return apiFetch<NoteNode[]>(`/notebook/${notebookId}/note/${noteId}/node`);
}

export function updateNode(
  notebookId: string,
  noteId: string,
  nodeId: string,
  payload: string,
  expectedVersion: number,
): Promise<NoteNode> {
  return apiFetch<NoteNode>(`/notebook/${notebookId}/note/${noteId}/node/${nodeId}`, {
    method: 'PATCH',
    body: JSON.stringify({
      type: 'update',
      payload,
      expected_version: expectedVersion,
    }),
  });
}
