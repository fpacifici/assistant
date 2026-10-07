import { apiFetch } from './client';
import type { SearchResponse } from '../types';

export const SEARCH_PAGE_SIZE = 20;

export interface SearchOptions {
  offset: number;
  limit: number;
  sort?: 'relevance' | 'updated';
}

/** Search the notes the caller can view (syntax: words, "phrases", tag:name). */
export function searchNotes(query: string, options: SearchOptions): Promise<SearchResponse> {
  const params = new URLSearchParams({
    q: query,
    offset: String(options.offset),
    limit: String(options.limit),
  });
  if (options.sort) params.set('sort', options.sort);
  return apiFetch<SearchResponse>(`/search/notes?${params}`);
}
