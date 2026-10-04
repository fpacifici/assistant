import { describe, it, expect, vi, beforeEach } from 'vitest';
import { addNoteTag, createTag, fetchTags, removeNoteTag } from './tags';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function okResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: true,
    status,
    json: () => Promise.resolve(body),
  } as Response);
}

function lastCall(): [string, RequestInit] {
  return mockFetch.mock.calls[mockFetch.mock.calls.length - 1] as [string, RequestInit];
}

describe('tags API', () => {
  beforeEach(() => vi.clearAllMocks());

  it('fetchTags GETs /tag', async () => {
    mockFetch.mockReturnValueOnce(okResponse([{ id: 't1', name: 'Work' }]));
    expect(await fetchTags()).toEqual([{ id: 't1', name: 'Work' }]);
    expect(lastCall()[0]).toMatch(/\/tag$/);
  });

  it('createTag POSTs the name', async () => {
    mockFetch.mockReturnValueOnce(okResponse({ id: 't1', name: 'Work' }, 201));
    await createTag('Work');
    const [url, init] = lastCall();
    expect(url).toMatch(/\/tag$/);
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body as string)).toEqual({ name: 'Work' });
  });

  it('addNoteTag sends tag_id for an existing tag', async () => {
    mockFetch.mockReturnValueOnce(okResponse([]));
    await addNoteTag('nb-1', 'note-1', { tagId: 't1' });
    const [url, init] = lastCall();
    expect(url).toMatch(/\/notebook\/nb-1\/note\/note-1\/tag$/);
    expect(JSON.parse(init.body as string)).toEqual({ tag_id: 't1' });
  });

  it('addNoteTag sends name to create a tag on the fly', async () => {
    mockFetch.mockReturnValueOnce(okResponse([]));
    await addNoteTag('nb-1', 'note-1', { name: 'Ideas' });
    expect(JSON.parse(lastCall()[1].body as string)).toEqual({ name: 'Ideas' });
  });

  it('removeNoteTag DELETEs the link', async () => {
    mockFetch.mockReturnValueOnce(okResponse(undefined, 204));
    await removeNoteTag('nb-1', 'note-1', 't1');
    const [url, init] = lastCall();
    expect(url).toMatch(/\/notebook\/nb-1\/note\/note-1\/tag\/t1$/);
    expect(init.method).toBe('DELETE');
  });
});
