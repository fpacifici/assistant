/**
 * Ask AI API (see docs/architecture/api.md#ask-ai): per-user threads and
 * answers streamed as server-sent events. The answer endpoint is a POST, so
 * it is read with `fetch` and parsed here rather than with `EventSource`.
 */

import { ApiError, apiFetch, apiUrl } from './client';

export interface AskStatus {
  enabled: boolean;
}

export interface ChatThread {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

/** A note an answer drew on. */
export interface AskSource {
  note_id: string;
  notebook_id: string;
  title: string;
  notebook_name: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources: AskSource[];
}

export interface ChatThreadDetail {
  thread: ChatThread;
  messages: ChatMessage[];
}

export type AskEvent =
  | { type: 'token'; text: string }
  | { type: 'tool'; name: string; status: 'start' | 'end'; input: Record<string, unknown> }
  | { type: 'sources'; sources: AskSource[] }
  | { type: 'error'; message: string }
  | { type: 'done' };

export function fetchAskStatus(): Promise<AskStatus> {
  return apiFetch<AskStatus>('/ask/status');
}

export function listThreads(): Promise<ChatThread[]> {
  return apiFetch<ChatThread[]>('/ask/threads?limit=100');
}

export function createThread(): Promise<ChatThread> {
  return apiFetch<ChatThread>('/ask/threads', { method: 'POST' });
}

export function fetchThread(id: string): Promise<ChatThreadDetail> {
  return apiFetch<ChatThreadDetail>(`/ask/threads/${id}`);
}

export function deleteThread(id: string): Promise<void> {
  return apiFetch<void>(`/ask/threads/${id}`, { method: 'DELETE' });
}

/** The URL of a note a source points to. */
export function sourceUrl(source: AskSource): string {
  return `/notebooks/${source.notebook_id}/notes/${source.note_id}`;
}

/**
 * Split server-sent event text into events.
 *
 * Returns the complete events in `buffer` and the unfinished tail, to be
 * prepended to the next chunk.
 */
export function parseSse(buffer: string): { events: AskEvent[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, '\n');
  const blocks = normalized.split('\n\n');
  const rest = blocks.pop() ?? '';
  const events: AskEvent[] = [];
  for (const block of blocks) {
    let type = 'message';
    const data: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) type = line.slice(6).trim();
      else if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
    }
    if (data.length === 0) continue;
    try {
      events.push({ type, ...JSON.parse(data.join('\n')) } as AskEvent);
    } catch {
      // Ignore malformed events rather than abort the whole answer.
    }
  }
  return { events, rest };
}

/**
 * Ask a question in a thread, calling `onEvent` for each streamed event.
 *
 * Resolves when the stream ends. Rejects with `ApiError` if the request
 * itself fails (e.g. 404, 503); failures while answering arrive as an
 * `error` event instead.
 */
export async function streamAnswer(
  threadId: string,
  question: string,
  onEvent: (event: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(apiUrl(`/ask/threads/${threadId}/messages`), {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ question }),
    signal,
  });
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail || response.statusText);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSse(buffer);
    buffer = parsed.rest;
    parsed.events.forEach(onEvent);
  }
  parseSse(buffer + decoder.decode() + '\n\n').events.forEach(onEvent);
}
