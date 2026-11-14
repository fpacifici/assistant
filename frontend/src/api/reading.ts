import { apiFetch } from './client';
import type {
  CategoryCount,
  LinkPage,
  LinkState,
  NoteSuggestion,
  PromoteResult,
  ReadingLink,
} from '../types';

/** Query key prefix of everything in the Reading tab. */
export const READING_KEY = ['reading'] as const;

/** Page size of a link list (the API caps `limit` at 100). */
export const LINK_PAGE_SIZE = 20;

/** Narrows a list to one category, or to Unfiled. */
export type LinkFilter = { categoryId: string } | { unfiled: true } | Record<string, never>;

/** Save a link. A URL already saved is a 409 whose `body.link_id` is the existing link. */
export function addLink(url: string): Promise<ReadingLink> {
  return apiFetch<ReadingLink>('/reading/link', {
    method: 'POST',
    body: JSON.stringify({ url }),
  });
}

export function fetchLink(id: string): Promise<ReadingLink> {
  return apiFetch<ReadingLink>(`/reading/link/${id}`);
}

/** Where a link is shown: its view, narrowed to its category, scrolled to the card. */
export function linkLocation(link: ReadingLink): string {
  const path = { to_read: '/reading', discarded: '/reading/archive', promoted: '/reading/promoted' }[
    link.state
  ];
  return `${path}?category=${link.category_id ?? 'unfiled'}#link-${link.id}`;
}

export function fetchLinks(
  state: LinkState,
  filter: LinkFilter,
  cursor?: string,
): Promise<LinkPage> {
  const params = new URLSearchParams({ state, limit: String(LINK_PAGE_SIZE) });
  if ('categoryId' in filter) params.set('category_id', filter.categoryId);
  if ('unfiled' in filter) params.set('unfiled', 'true');
  if (cursor) params.set('cursor', cursor);
  return apiFetch<LinkPage>(`/reading/link?${params}`);
}

/** How many links of a state each category has. Empty categories are absent. */
export function fetchLinkCounts(state: LinkState): Promise<CategoryCount[]> {
  return apiFetch<CategoryCount[]>(`/reading/link/counts?state=${state}`);
}

export interface LinkChanges {
  /** Null or blank goes back to the automatic title. */
  title?: string | null;
  /** Null is Unfiled. */
  category_id?: string | null;
  user_notes?: string | null;
}

/** Edit a link. A title or category set here wins over the analysis. */
export function updateLink(id: string, changes: LinkChanges): Promise<ReadingLink> {
  return apiFetch<ReadingLink>(`/reading/link/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
  });
}

function linkAction(id: string, action: string): Promise<ReadingLink> {
  return apiFetch<ReadingLink>(`/reading/link/${id}/${action}`, { method: 'POST' });
}

export function discardLink(id: string): Promise<ReadingLink> {
  return linkAction(id, 'discard');
}

export function restoreLink(id: string): Promise<ReadingLink> {
  return linkAction(id, 'restore');
}

/** Analyze again: the category is chosen again, an edited title is kept. */
export function retryLink(id: string): Promise<ReadingLink> {
  return linkAction(id, 'retry');
}

/** Delete a discarded or promoted link. */
export function deleteLink(id: string): Promise<void> {
  return apiFetch<void>(`/reading/link/${id}`, { method: 'DELETE' });
}

/** Up to 5 notes the user can edit about the link's topic. */
export function fetchSuggestions(id: string): Promise<NoteSuggestion[]> {
  return apiFetch<NoteSuggestion[]>(`/reading/link/${id}/suggestions`);
}

export type PromoteTarget = { noteId: string } | { notebookId: string; title: string };

/** Mark a link promoted to a note, existing or new. Nothing is written into the note. */
export function promoteLink(id: string, target: PromoteTarget): Promise<PromoteResult> {
  const body =
    'noteId' in target
      ? { note_id: target.noteId }
      : { notebook_id: target.notebookId, title: target.title };
  return apiFetch<PromoteResult>(`/reading/link/${id}/promote`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}
