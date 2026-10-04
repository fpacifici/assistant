import { apiFetch } from './client';
import type { Tag } from '../types';

/** The caller's tag vocabulary, ordered by name. */
export function fetchTags(): Promise<Tag[]> {
  return apiFetch<Tag[]>('/tag');
}

/** Create a tag, or return the existing one with the same normalized name. */
export function createTag(name: string): Promise<Tag> {
  return apiFetch<Tag>('/tag', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

/**
 * Tag a note with an existing tag (`tagId`) or by name (`name`), creating the
 * tag on the fly. Returns the caller's tags on the note after the change.
 */
export function addNoteTag(
  notebookId: string,
  noteId: string,
  tag: { tagId: string } | { name: string },
): Promise<Tag[]> {
  const body = 'tagId' in tag ? { tag_id: tag.tagId } : { name: tag.name };
  return apiFetch<Tag[]>(`/notebook/${notebookId}/note/${noteId}/tag`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function removeNoteTag(
  notebookId: string,
  noteId: string,
  tagId: string,
): Promise<void> {
  return apiFetch<void>(`/notebook/${notebookId}/note/${noteId}/tag/${tagId}`, {
    method: 'DELETE',
  });
}
