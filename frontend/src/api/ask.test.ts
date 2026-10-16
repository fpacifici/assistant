import { describe, it, expect, vi, afterEach } from 'vitest';
import { parseSse, sourceUrl, streamAnswer } from './ask';
import type { AskEvent } from './ask';
import { ApiError } from './client';

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { 'Content-Type': 'text/event-stream' } });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// --- parseSse ---

describe('parseSse', () => {
  it('parses complete events and keeps the unfinished tail', () => {
    const { events, rest } = parseSse(
      'event: token\ndata: {"text": "Hi"}\n\nevent: done\ndata: {}\n\nevent: tok',
    );

    expect(events).toEqual([{ type: 'token', text: 'Hi' }, { type: 'done' }]);
    expect(rest).toBe('event: tok');
  });

  it('accepts CRLF line endings', () => {
    const { events } = parseSse('event: error\r\ndata: {"message": "No credits"}\r\n\r\n');

    expect(events).toEqual([{ type: 'error', message: 'No credits' }]);
  });

  it('skips malformed events and blocks without data', () => {
    const { events } = parseSse('event: token\ndata: {oops\n\n: comment\n\nevent: done\ndata: {}\n\n');

    expect(events).toEqual([{ type: 'done' }]);
  });
});

// --- streamAnswer ---

describe('streamAnswer', () => {
  it('posts the question and reports events split across chunks', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([
        'event: tool\ndata: {"name": "search_notes", "status": "start", "input": {"query": "q"}}\n\neve',
        'nt: token\ndata: {"text": "In Rome"}\n\n',
        'event: done\ndata: {}\n\n',
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);
    const events: AskEvent[] = [];

    await streamAnswer('t1', 'Where?', (e) => events.push(e));

    expect(fetchMock).toHaveBeenCalledWith(
      'http://localhost:8000/ask/threads/t1/messages',
      expect.objectContaining({
        method: 'POST',
        credentials: 'include',
        body: JSON.stringify({ question: 'Where?' }),
      }),
    );
    expect(events).toEqual([
      { type: 'tool', name: 'search_notes', status: 'start', input: { query: 'q' } },
      { type: 'token', text: 'In Rome' },
      { type: 'done' },
    ]);
  });

  it('reports a final event without a trailing blank line', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(['event: done\ndata: {}'])));
    const events: AskEvent[] = [];

    await streamAnswer('t1', 'Where?', (e) => events.push(e));

    expect(events).toEqual([{ type: 'done' }]);
  });

  it('rejects with the API error when the request fails', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: 'AI features are disabled' }), { status: 503 }),
      ),
    );

    const error = await streamAnswer('t1', 'Where?', () => {}).catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(503);
    expect((error as ApiError).message).toBe('AI features are disabled');
  });
});

describe('sourceUrl', () => {
  it('links to the note in its notebook', () => {
    expect(
      sourceUrl({ note_id: 'n1', notebook_id: 'nb1', title: 'Rome', notebook_name: 'Travel' }),
    ).toBe('/notebooks/nb1/notes/n1');
  });
});
