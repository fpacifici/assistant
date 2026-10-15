/**
 * One Ask AI conversation: the stored messages, the answer being streamed,
 * and the question box. Without a `threadId` it is a new chat: the thread is
 * created on the first question and reported with `onThreadCreated` once the
 * answer is complete.
 *
 * Answers are markdown, shown as plain text (whitespace preserved).
 */

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { createThread, fetchThread, sourceUrl, streamAnswer } from '../api/ask';
import type {
  AskEvent,
  AskSource,
  ChatMessage,
  ChatThread,
  ChatThreadDetail,
} from '../api/ask';
import { ApiError } from '../api/client';

const TOOL_LABELS: Record<string, string> = {
  search_notes: 'Searching your notes…',
  keyword_search: 'Looking for exact words…',
  get_note: 'Reading a note…',
};

interface Pending {
  question: string;
  answer: string;
  tool: string | null;
  sources: AskSource[];
  error: string | null;
}

function Sources({ sources }: { sources: AskSource[] }) {
  if (sources.length === 0) return null;
  return (
    <div className="ask-sources">
      <span className="ask-sources-label">Sources</span>
      <ul>
        {sources.map((source) => (
          <li key={source.note_id}>
            <Link to={sourceUrl(source)}>{source.title || 'Untitled'}</Link>
            <span className="ask-source-notebook">{source.notebook_name}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Message({ message }: { message: ChatMessage }) {
  return (
    <div className={`ask-message ask-message-${message.role}`}>
      <div className="ask-message-text">{message.content}</div>
      {message.role === 'assistant' && <Sources sources={message.sources} />}
    </div>
  );
}

interface AskConversationProps {
  threadId: string | null;
  onThreadCreated: (id: string) => void;
}

export default function AskConversation({ threadId, onThreadCreated }: AskConversationProps) {
  const queryClient = useQueryClient();
  const [question, setQuestion] = useState('');
  const [pending, setPending] = useState<Pending | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['ask', 'thread', threadId],
    queryFn: () => fetchThread(threadId!),
    enabled: threadId !== null,
  });
  const messages = data?.messages ?? [];

  useEffect(() => () => abortRef.current?.abort(), []);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: 'end' });
  }, [messages.length, pending?.answer, pending?.tool]);

  const ask = async (text: string) => {
    const controller = new AbortController();
    abortRef.current = controller;
    let current: Pending = { question: text, answer: '', tool: null, sources: [], error: null };
    setPending(current);
    const update = (patch: Partial<Pending>) => {
      current = { ...current, ...patch };
      setPending(current);
    };
    const onEvent = (event: AskEvent) => {
      if (event.type === 'token') update({ answer: current.answer + event.text });
      else if (event.type === 'tool') update({ tool: event.status === 'start' ? event.name : null });
      else if (event.type === 'sources') update({ sources: event.sources });
      else if (event.type === 'error') update({ error: event.message, tool: null });
    };

    let id = threadId;
    let created: ChatThread | null = null;
    try {
      if (id === null) {
        created = await createThread();
        id = created.id;
      }
      await streamAnswer(id, text, onEvent, controller.signal);
    } catch (err) {
      if (controller.signal.aborted) return;
      const message =
        err instanceof ApiError && err.status === 503
          ? 'Ask AI is not available on this server.'
          : 'Could not reach the server. Try again.';
      update({ error: message, tool: null });
      return;
    }
    if (current.error || id === null) {
      // The thread exists even though answering failed: list it.
      if (created) void queryClient.invalidateQueries({ queryKey: ['ask', 'threads'] });
      return;
    }

    // Show the finished exchange from the cache right away, then refetch.
    const key = ['ask', 'thread', id];
    const exchange: ChatMessage[] = [
      { role: 'user', content: text, sources: [] },
      { role: 'assistant', content: current.answer, sources: current.sources },
    ];
    queryClient.setQueryData<ChatThreadDetail>(key, (old) => {
      if (old) return { ...old, messages: [...old.messages, ...exchange] };
      return created ? { thread: created, messages: exchange } : old;
    });
    void queryClient.invalidateQueries({ queryKey: key });
    void queryClient.invalidateQueries({ queryKey: ['ask', 'threads'] });
    setPending(null);
    if (id !== threadId) onThreadCreated(id);
  };

  const streaming = pending !== null && pending.error === null;

  const submit = () => {
    const text = question.trim();
    if (!text || streaming) return;
    setQuestion('');
    void ask(text);
  };

  return (
    <section className="ask-conversation" aria-label="Conversation">
      <div className="ask-messages">
        {threadId === null && !pending && (
          <p className="search-status">
            Ask a question about your notes. The answer is based only on the notes you can see,
            and lists the notes it used.
          </p>
        )}
        {isLoading && <p className="search-status">Loading…</p>}
        {isError && <p className="ask-error">Could not load this chat.</p>}
        {messages.map((message, i) => (
          <Message key={i} message={message} />
        ))}
        {pending && (
          <>
            <Message message={{ role: 'user', content: pending.question, sources: [] }} />
            <div className="ask-message ask-message-assistant" aria-live="polite">
              {pending.answer && <div className="ask-message-text">{pending.answer}</div>}
              {pending.tool && (
                <div className="ask-tool">{TOOL_LABELS[pending.tool] ?? 'Working…'}</div>
              )}
              {!pending.answer && !pending.tool && !pending.error && (
                <div className="ask-tool">Thinking…</div>
              )}
              {pending.error && <div className="ask-error">{pending.error}</div>}
              <Sources sources={pending.sources} />
            </div>
          </>
        )}
        <div ref={endRef} />
      </div>
      <form
        className="ask-composer"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <textarea
          aria-label="Question"
          placeholder="Ask about your notes…"
          value={question}
          rows={2}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button type="submit" className="ask-send" disabled={streaming || !question.trim()}>
          {streaming ? 'Answering…' : 'Ask'}
        </button>
      </form>
    </section>
  );
}
