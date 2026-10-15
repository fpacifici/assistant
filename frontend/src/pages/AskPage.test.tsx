import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AskPage from './AskPage';
import { renderWithProviders } from '../test/renderWithProviders';
import type { AskEvent, ChatMessage, ChatThread } from '../api/ask';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { uid: 'u1', email: 'a@b.com', firstname: 'A', lastname: 'B', invite_quota_remaining: 1 },
    logout: vi.fn(),
  }),
}));

vi.mock('../api/invites', () => ({
  fetchInvitesConfig: vi.fn().mockResolvedValue({
    registration_enabled: true,
    invites_enabled: false,
  }),
}));

vi.mock('../api/ask', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/ask')>()),
  fetchAskStatus: vi.fn(),
  listThreads: vi.fn(),
  createThread: vi.fn(),
  fetchThread: vi.fn(),
  deleteThread: vi.fn(),
  streamAnswer: vi.fn(),
}));

import {
  createThread,
  deleteThread,
  fetchAskStatus,
  fetchThread,
  listThreads,
  streamAnswer,
} from '../api/ask';

const ROME = { note_id: 'n1', notebook_id: 'nb1', title: 'Rome', notebook_name: 'Travel' };

function thread(id: string, title: string): ChatThread {
  return { id, title, created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z' };
}

/**
 * Make `streamAnswer` replay these events, and `fetchThread` return `after`
 * once a question was asked (as the server stores the exchange).
 */
function answerWith(events: AskEvent[], after: ChatMessage[] = []) {
  vi.mocked(streamAnswer).mockImplementation(async (_id, _question, onEvent) => {
    events.forEach(onEvent);
  });
  vi.mocked(fetchThread).mockImplementation(async (id) => ({
    thread: thread(id, 'Asked'),
    messages: vi.mocked(streamAnswer).mock.calls.length > 0 ? after : [],
  }));
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchAskStatus).mockResolvedValue({ enabled: true });
  vi.mocked(listThreads).mockResolvedValue([thread('t1', 'Rome trip'), thread('t2', '')]);
  vi.mocked(fetchThread).mockResolvedValue({ thread: thread('t1', 'Rome trip'), messages: [] });
});

// --- Availability ---

describe('AskPage availability', () => {
  it('explains when AI is disabled on the server', async () => {
    vi.mocked(fetchAskStatus).mockResolvedValue({ enabled: false });

    renderWithProviders(<AskPage />, { initialEntries: ['/ask'] });

    expect(await screen.findByText(/not available on this server/i)).toBeInTheDocument();
    expect(listThreads).not.toHaveBeenCalled();
    expect(screen.queryByRole('link', { name: 'Ask AI' })).not.toBeInTheDocument();
  });

  it('links Ask AI from the desktop header when enabled', async () => {
    renderWithProviders(<AskPage />, { initialEntries: ['/ask'] });

    expect(await screen.findByRole('link', { name: 'Ask AI' })).toHaveAttribute('href', '/ask');
  });
});

// --- Threads ---

describe('AskPage threads', () => {
  it('lists the threads and opens the one in the URL', async () => {
    vi.mocked(fetchThread).mockResolvedValue({
      thread: thread('t1', 'Rome trip'),
      messages: [
        { role: 'user', content: 'When was I in Rome?', sources: [] },
        { role: 'assistant', content: 'In May.', sources: [ROME] },
      ],
    });

    renderWithProviders(<AskPage />, { initialEntries: ['/ask?thread=t1'] });

    const chats = await screen.findByRole('navigation', { name: 'Chats' });
    expect(await within(chats).findByRole('link', { name: 'Rome trip' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(within(chats).getByRole('link', { name: 'New chat' })).toBeInTheDocument();
    expect(await screen.findByText('In May.')).toBeInTheDocument();
    expect(screen.getByText('When was I in Rome?')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Rome' })).toHaveAttribute(
      'href',
      '/notebooks/nb1/notes/n1',
    );
    expect(fetchThread).toHaveBeenCalledWith('t1');
  });

  it('deletes a thread after confirmation', async () => {
    const user = userEvent.setup();
    vi.mocked(deleteThread).mockResolvedValue();
    const { router } = renderWithProviders(<AskPage />, { initialEntries: ['/ask?thread=t1'] });

    await user.click(await screen.findByRole('button', { name: 'Delete chat Rome trip' }));
    await user.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(deleteThread).toHaveBeenCalledWith('t1'));
    await waitFor(() => expect(router.state.location.search).toBe(''));
  });
});

// --- Asking ---

describe('AskPage asking', () => {
  it('creates a thread on the first question and streams the answer', async () => {
    const user = userEvent.setup();
    vi.mocked(createThread).mockResolvedValue(thread('t9', ''));
    answerWith([
      { type: 'tool', name: 'search_notes', status: 'start', input: { query: 'rome' } },
      { type: 'tool', name: 'search_notes', status: 'end', input: {} },
      { type: 'token', text: 'You were in Rome ' },
      { type: 'token', text: 'in May.' },
      { type: 'sources', sources: [ROME] },
      { type: 'done' },
    ], [
      { role: 'user', content: 'When was I in Rome?', sources: [] },
      { role: 'assistant', content: 'You were in Rome in May.', sources: [ROME] },
    ]);
    const { router } = renderWithProviders(<AskPage />, { initialEntries: ['/ask'] });

    await user.type(await screen.findByRole('textbox', { name: 'Question' }), 'When was I in Rome?');
    await user.click(screen.getByRole('button', { name: 'Ask' }));

    await waitFor(() => expect(router.state.location.search).toBe('?thread=t9'));
    expect(streamAnswer).toHaveBeenCalledWith(
      't9',
      'When was I in Rome?',
      expect.any(Function),
      expect.any(AbortSignal),
    );
    expect(await screen.findByText('You were in Rome in May.')).toBeInTheDocument();
    expect(screen.getByText('When was I in Rome?')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Rome' })).toHaveAttribute(
      'href',
      '/notebooks/nb1/notes/n1',
    );
  });

  it('asks in the open thread with Enter', async () => {
    const user = userEvent.setup();
    answerWith(
      [{ type: 'token', text: 'Yes.' }, { type: 'sources', sources: [] }, { type: 'done' }],
      [
        { role: 'user', content: 'Again?', sources: [] },
        { role: 'assistant', content: 'Yes.', sources: [] },
      ],
    );
    renderWithProviders(<AskPage />, { initialEntries: ['/ask?thread=t1'] });

    await user.type(await screen.findByRole('textbox', { name: 'Question' }), 'Again?{Enter}');

    await waitFor(() =>
      expect(streamAnswer).toHaveBeenCalledWith(
        't1',
        'Again?',
        expect.any(Function),
        expect.any(AbortSignal),
      ),
    );
    expect(createThread).not.toHaveBeenCalled();
    expect(await screen.findByText('Yes.')).toBeInTheDocument();
  });

  it('shows the progress of a tool call while answering', async () => {
    const user = userEvent.setup();
    let finish: () => void = () => {};
    vi.mocked(streamAnswer).mockImplementation(
      (_id, _q, onEvent) =>
        new Promise<void>((resolve) => {
          onEvent({ type: 'tool', name: 'get_note', status: 'start', input: { note_id: 'n1' } });
          finish = resolve;
        }),
    );
    renderWithProviders(<AskPage />, { initialEntries: ['/ask?thread=t1'] });

    await user.type(await screen.findByRole('textbox', { name: 'Question' }), 'Read it{Enter}');

    expect(await screen.findByText('Reading a note…')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Answering…' })).toBeDisabled();
    finish();
  });

  it('shows errors streamed by the server', async () => {
    const user = userEvent.setup();
    answerWith([
      { type: 'error', message: 'The AI service has no credits left.' },
      { type: 'done' },
    ]);
    renderWithProviders(<AskPage />, { initialEntries: ['/ask?thread=t1'] });

    await user.type(await screen.findByRole('textbox', { name: 'Question' }), 'Hi{Enter}');

    expect(await screen.findByText('The AI service has no credits left.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ask' })).toBeInTheDocument();
  });
});

// --- Mobile ---

describe('AskPage on mobile', () => {
  it('shows the thread list without a thread, and the conversation with one', async () => {
    const { router } = renderWithProviders(<AskPage />, {
      initialEntries: ['/ask'],
      layout: 'mobile',
    });

    expect(await screen.findByRole('link', { name: 'Rome trip' })).toBeInTheDocument();
    expect(screen.queryByRole('textbox', { name: 'Question' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back' })).toHaveAttribute('href', '/notebooks');

    await router.navigate('/ask?thread=new');

    expect(await screen.findByRole('textbox', { name: 'Question' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back' })).toHaveAttribute('href', '/ask');
  });
});
