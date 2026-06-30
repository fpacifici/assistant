import { apiFetch } from './client';
import type { NoteNode } from '../types';

export function fetchNodes(notebookId: string, noteId: string): Promise<NoteNode[]> {
  return apiFetch<NoteNode[]>(`/notebook/${notebookId}/note/${noteId}/node`);
}

export interface NodeCreateOpts {
  payload?: string;
  blockType?: string;
  afterNodeId?: string;
  beforeNodeId?: string;
  file_id?: string;
}

export function createNode(
  notebookId: string,
  noteId: string,
  opts: NodeCreateOpts,
): Promise<NoteNode> {
  const body: Record<string, string> = {};
  if (opts.payload !== undefined) body.payload = opts.payload;
  if (opts.blockType) body.block_type = opts.blockType;
  if (opts.afterNodeId) body.after_node_id = opts.afterNodeId;
  if (opts.beforeNodeId) body.before_node_id = opts.beforeNodeId;
  if (opts.file_id) body.file_id = opts.file_id;
  return apiFetch<NoteNode>(`/notebook/${notebookId}/note/${noteId}/node`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function updateNode(
  notebookId: string,
  noteId: string,
  nodeId: string,
  payload: string,
  expectedVersion: number,
  blockType?: string,
): Promise<NoteNode> {
  const body: Record<string, unknown> = {
    type: 'update',
    payload,
    expected_version: expectedVersion,
  };
  if (blockType !== undefined) body.block_type = blockType;
  return apiFetch<NoteNode>(`/notebook/${notebookId}/note/${noteId}/node/${nodeId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  });
}

export function deleteNode(
  notebookId: string,
  noteId: string,
  nodeId: string,
): Promise<void> {
  return apiFetch<void>(`/notebook/${notebookId}/note/${noteId}/node/${nodeId}`, {
    method: 'DELETE',
  });
}
