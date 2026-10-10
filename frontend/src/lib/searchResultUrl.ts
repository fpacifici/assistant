import type { SearchResult } from '../types';

/** The note of a search result, opened at block `nodeId` when given (see NoteEditor `?node=`). */
export function searchResultUrl(result: SearchResult, nodeId?: string): string {
  const base = `/notebooks/${result.note.notebook_id}/notes/${result.note.id}`;
  return nodeId ? `${base}?node=${encodeURIComponent(nodeId)}` : base;
}
