import { apiFetch } from './client';
import type {
  CollectionRun,
  CollectionRunDetail,
  BlogPost,
  BlogSource,
  PostPage,
  PostState,
  PostView,
  Tag,
} from '../types';

/** Page size of the post list (the API caps `limit` at 100). */
export const POST_PAGE_SIZE = 20;

/** The largest bulk verdict the API takes at once. */
export const MAX_BULK_POSTS = 500;

// --- Sources ---

/** Active sources, or with `archived` those that still have useful posts. */
export function fetchSources({ archived = false } = {}): Promise<BlogSource[]> {
  return apiFetch<BlogSource[]>(`/blog/source${archived ? '?archived=true' : ''}`);
}

export function fetchSource(id: string): Promise<BlogSource> {
  return apiFetch<BlogSource>(`/blog/source/${id}`);
}

export interface SourceInput {
  url: string;
  title?: string;
  remarks?: string;
  preferences?: string;
  category_id?: string | null;
  lookback_days?: number;
}

/** Register a source. The server resolves the URL before answering. */
export function createSource(input: SourceInput): Promise<BlogSource> {
  return apiFetch<BlogSource>('/blog/source', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export interface SourceChanges {
  title?: string;
  remarks?: string;
  preferences?: string;
  category_id?: string | null;
  enabled?: boolean;
}

export function updateSource(id: string, changes: SourceChanges): Promise<BlogSource> {
  return apiFetch<BlogSource>(`/blog/source/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(changes),
  });
}

/** Delete a source and its posts, or with `keepUseful` archive it. */
export function deleteSource(id: string, keepUseful: boolean): Promise<void> {
  return apiFetch<void>(`/blog/source/${id}?keep_useful=${keepUseful}`, { method: 'DELETE' });
}

// --- Collection log ---

/** The latest runs of a source, newest first. */
export function fetchRuns(sourceId: string): Promise<CollectionRun[]> {
  return apiFetch<CollectionRun[]>(`/blog/source/${sourceId}/run`);
}

export function fetchRun(sourceId: string, runId: string): Promise<CollectionRunDetail> {
  return apiFetch<CollectionRunDetail>(`/blog/source/${sourceId}/run/${runId}`);
}

/** Collect a source now. Answers at once with the run, which fills in as it goes. */
export function refreshSource(sourceId: string): Promise<CollectionRun> {
  return apiFetch<CollectionRun>(`/blog/source/${sourceId}/refresh`, { method: 'POST' });
}

// --- Posts ---

export interface PostFilters {
  categoryId?: string;
  unfiled?: boolean;
  sourceId?: string;
  tagId?: string;
  /** True for read posts only, false for those still to read. */
  read?: boolean;
}

export function fetchPosts(
  view: PostView,
  filters: PostFilters,
  cursor?: string,
): Promise<PostPage> {
  const params = new URLSearchParams({ view, limit: String(POST_PAGE_SIZE) });
  if (filters.categoryId) params.set('category_id', filters.categoryId);
  if (filters.unfiled) params.set('unfiled', 'true');
  if (filters.sourceId) params.set('source_id', filters.sourceId);
  if (filters.tagId) params.set('tag', filters.tagId);
  if (filters.read !== undefined) params.set('read', String(filters.read));
  if (cursor) params.set('cursor', cursor);
  return apiFetch<PostPage>(`/blog/post?${params}`);
}

export function setPostState(id: string, state: PostState): Promise<BlogPost> {
  return apiFetch<BlogPost>(`/blog/post/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ state }),
  });
}

/** Mark a post read, or back to read later. The verdict stays. */
export function setPostRead(id: string, read: boolean): Promise<BlogPost> {
  return apiFetch<BlogPost>(`/blog/post/${id}/read`, {
    method: 'PUT',
    body: JSON.stringify({ read }),
  });
}

/** Set the verdict of the listed posts: never more than the user has on screen. */
export function setPostsState(ids: string[], state: PostState): Promise<{ updated: number }> {
  return apiFetch<{ updated: number }>('/blog/post/bulk-state', {
    method: 'POST',
    body: JSON.stringify({ post_ids: ids, state }),
  });
}

/** Tag a post by id or by name. Returns the post's tags after the change. */
export function addPostTag(
  postId: string,
  tag: { tagId: string } | { name: string },
): Promise<Tag[]> {
  const body = 'tagId' in tag ? { tag_id: tag.tagId } : { name: tag.name };
  return apiFetch<Tag[]>(`/blog/post/${postId}/tag`, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export function removePostTag(postId: string, tagId: string): Promise<void> {
  return apiFetch<void>(`/blog/post/${postId}/tag/${tagId}`, { method: 'DELETE' });
}
