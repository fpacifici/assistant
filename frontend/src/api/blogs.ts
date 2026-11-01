import { apiFetch } from './client';
import type {
  BlogDirectory,
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

// --- Directories ---

export function fetchDirectories(): Promise<BlogDirectory[]> {
  return apiFetch<BlogDirectory[]>('/blog/directory');
}

export function createDirectory(name: string): Promise<BlogDirectory> {
  return apiFetch<BlogDirectory>('/blog/directory', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function renameDirectory(id: string, name: string): Promise<BlogDirectory> {
  return apiFetch<BlogDirectory>(`/blog/directory/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  });
}

/** Delete a directory. Its sources move to Unfiled. */
export function deleteDirectory(id: string): Promise<void> {
  return apiFetch<void>(`/blog/directory/${id}`, { method: 'DELETE' });
}

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
  directory_id?: string | null;
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
  directory_id?: string | null;
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

// --- Posts ---

export interface PostFilters {
  directoryId?: string;
  unfiled?: boolean;
  sourceId?: string;
  tagId?: string;
}

export function fetchPosts(
  view: PostView,
  filters: PostFilters,
  cursor?: string,
): Promise<PostPage> {
  const params = new URLSearchParams({ view, limit: String(POST_PAGE_SIZE) });
  if (filters.directoryId) params.set('directory_id', filters.directoryId);
  if (filters.unfiled) params.set('unfiled', 'true');
  if (filters.sourceId) params.set('source_id', filters.sourceId);
  if (filters.tagId) params.set('tag', filters.tagId);
  if (cursor) params.set('cursor', cursor);
  return apiFetch<PostPage>(`/blog/post?${params}`);
}

export function setPostState(id: string, state: PostState): Promise<BlogPost> {
  return apiFetch<BlogPost>(`/blog/post/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ state }),
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
