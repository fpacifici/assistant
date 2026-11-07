import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiFetch } from './client';
import {
  addPostTag,
  deleteSource,
  fetchPosts,
  fetchSources,
  setPostRead,
  setPostsState,
} from './blogs';

vi.mock('./client', () => ({ apiFetch: vi.fn() }));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('fetchPosts', () => {
  it('sends the view and page size', () => {
    void fetchPosts('new', {});
    expect(apiFetch).toHaveBeenCalledWith('/blog/post?view=new&limit=20');
  });

  it('sends every filter and the cursor', () => {
    void fetchPosts('all', { directoryId: 'd', sourceId: 's', tagId: 't', unfiled: true }, 'c');
    expect(apiFetch).toHaveBeenCalledWith(
      '/blog/post?view=all&limit=20&directory_id=d&unfiled=true&source_id=s&tag=t&cursor=c',
    );
  });

  it('sends the read filter, false included', () => {
    void fetchPosts('relevant', { read: false });
    expect(apiFetch).toHaveBeenCalledWith('/blog/post?view=relevant&limit=20&read=false');
  });
});

describe('sources', () => {
  it('lists archived sources on request', () => {
    void fetchSources({ archived: true });
    expect(apiFetch).toHaveBeenCalledWith('/blog/source?archived=true');
  });

  it('says whether to keep useful posts', () => {
    void deleteSource('s1', true);
    expect(apiFetch).toHaveBeenCalledWith('/blog/source/s1?keep_useful=true', {
      method: 'DELETE',
    });
  });
});

describe('posts', () => {
  it('marks a post read', () => {
    void setPostRead('p', true);
    expect(apiFetch).toHaveBeenCalledWith('/blog/post/p/read', {
      method: 'PUT',
      body: JSON.stringify({ read: true }),
    });
  });

  it('sends bulk verdicts by id', () => {
    void setPostsState(['a', 'b'], 'not_useful');
    expect(apiFetch).toHaveBeenCalledWith('/blog/post/bulk-state', {
      method: 'POST',
      body: JSON.stringify({ post_ids: ['a', 'b'], state: 'not_useful' }),
    });
  });

  it('tags by id or by name', () => {
    void addPostTag('p', { tagId: 't' });
    void addPostTag('p', { name: 'Work' });
    const bodies = vi.mocked(apiFetch).mock.calls.map(([, options]) => options?.body);
    expect(bodies).toEqual([
      JSON.stringify({ tag_id: 't' }),
      JSON.stringify({ name: 'Work' }),
    ]);
  });
});
