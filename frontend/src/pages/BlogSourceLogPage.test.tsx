import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BlogSourceLogPage, { POLL_MS } from './BlogSourceLogPage';
import { ApiError } from '../api/client';
import { renderWithProviders } from '../test/renderWithProviders';
import type { BlogSource, CollectionEntry, CollectionRun, CollectionRunDetail } from '../types';

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

vi.mock('../api/ask', () => ({ fetchAskStatus: vi.fn().mockResolvedValue({ enabled: true }) }));

vi.mock('../api/blogs', () => ({
  fetchSource: vi.fn(),
  fetchRuns: vi.fn(),
  fetchRun: vi.fn(),
  refreshSource: vi.fn(),
}));

import { fetchRun, fetchRuns, fetchSource, refreshSource } from '../api/blogs';

const SOURCE = {
  id: 's1',
  title: 'Example Blog',
  feed_url: 'https://blog.example.com/feed.xml',
  kind: 'feed',
  preferences: 'Databases',
  collect_since: '2026-10-01T00:00:00Z',
  enabled: true,
} as BlogSource;

function run(id: string, fields: Partial<CollectionRun> = {}): CollectionRun {
  return {
    id,
    source_id: 's1',
    trigger: 'job',
    started_at: '2026-10-02T08:00:00Z',
    finished_at: '2026-10-02T08:01:00Z',
    outcome: 'collected',
    error: null,
    interrupted: false,
    entries_found: 2,
    verdicts: { new: 1, stored: 1 },
    ...fields,
  };
}

function entry(id: string, fields: Partial<CollectionEntry> = {}): CollectionEntry {
  return {
    id,
    url: `https://blog.example.com/${id}`,
    title: `Post ${id}`,
    published_at: '2026-10-01T12:00:00Z',
    verdict: 'stored',
    post_id: null,
    feed_text_chars: null,
    analysis: null,
    text_source: null,
    text_chars: null,
    error: null,
    summary: null,
    match_level: null,
    motivation: null,
    analyzed_at: null,
    ...fields,
  };
}

function detail(base: CollectionRun, entries: CollectionEntry[]): CollectionRunDetail {
  return { ...base, entries };
}

const ANALYZED = entry('a', {
  verdict: 'new',
  post_id: 'p1',
  feed_text_chars: 480,
  analysis: 'processed',
  text_source: 'page',
  text_chars: 2300,
  summary: 'What the model said.',
  match_level: 'high',
  motivation: 'It is about databases.',
});

function render(path = '/blogs/sources/s1/log') {
  return renderWithProviders(null, {
    initialEntries: [path],
    routes: [{ path: '/blogs/sources/:sourceId/log', element: <BlogSourceLogPage /> }],
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchSource).mockResolvedValue(SOURCE);
  vi.mocked(fetchRuns).mockResolvedValue([run('r2'), run('r1', { started_at: '2026-10-01T08:00:00Z' })]);
  vi.mocked(fetchRun).mockImplementation(async (_s, id) =>
    detail(run(id), [ANALYZED, entry('b')]),
  );
});

afterEach(() => {
  vi.useRealTimers();
});

// --- The log ---

describe('BlogSourceLogPage', () => {
  it('shows the source and opens the newest run', async () => {
    render();

    expect(await screen.findByRole('heading', { name: 'Example Blog' })).toBeInTheDocument();
    expect(screen.getByText('Preferences: Databases')).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: 'Post a' })).toBeInTheDocument();
    expect(fetchRun).toHaveBeenCalledWith('s1', 'r2');
    expect(fetchRuns).toHaveBeenCalledWith('s1');
  });

  it('shows each entry with its verdict and what the model did', async () => {
    render();

    const card = (await screen.findByRole('link', { name: 'Post a' })).closest('li')!;
    expect(within(card).getByText('New post')).toBeInTheDocument();
    expect(within(card).getByText('feed text: 480 characters')).toBeInTheDocument();
    expect(
      within(card).getByText('Summarized · text from the page, 2,300 characters'),
    ).toBeInTheDocument();
    expect(within(card).getByText('high match')).toBeInTheDocument();
    expect(within(card).getByText('What the model said.')).toBeInTheDocument();
    expect(within(card).getByText('It is about databases.')).toBeInTheDocument();

    const stored = screen.getByRole('link', { name: 'Post b' }).closest('li')!;
    expect(within(stored).getByText('Already collected')).toBeInTheDocument();
  });

  it('opens the original post in a new tab, safely', async () => {
    vi.mocked(fetchRun).mockResolvedValue(
      detail(run('r2'), [entry('a'), entry('x', { url: 'javascript:alert(1)', title: 'Evil' })]),
    );
    render();

    const link = await screen.findByRole('link', { name: 'Post a' });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
    expect(screen.getByText('Evil')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Evil' })).not.toBeInTheDocument();
  });

  it('shows why the model failed', async () => {
    vi.mocked(fetchRun).mockResolvedValue(
      detail(run('r2'), [
        entry('a', { verdict: 'new', analysis: 'error', error: 'Could not analyze (RateLimitError)' }),
      ]),
    );
    render();

    expect(await screen.findByText('Analysis failed: tried next run')).toBeInTheDocument();
    expect(screen.getByText('Could not analyze (RateLimitError)')).toBeInTheDocument();
  });

  it('shows a failed run with its error', async () => {
    vi.mocked(fetchRun).mockResolvedValue(
      detail(run('r2', { outcome: 'failed', error: 'HTTP 500', entries_found: 0 }), []),
    );
    render();

    expect(await screen.findByText('HTTP 500')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: /Failed/ })).toBeInTheDocument();
    expect(screen.getByText('The source listed nothing.')).toBeInTheDocument();
  });

  it('opens another run', async () => {
    const user = userEvent.setup();
    const { router } = render();
    const runs = await screen.findByRole('navigation', { name: 'Runs' });

    const [, older] = within(runs).getAllByRole('button');
    await user.click(older);

    expect(router.state.location.search).toBe('?run=r1');
    await waitFor(() => expect(fetchRun).toHaveBeenCalledWith('s1', 'r1'));
  });

  it('hides posts already collected on request, but not retries', async () => {
    vi.mocked(fetchRun).mockResolvedValue(
      detail(run('r2'), [
        ANALYZED,
        entry('b'),
        entry('c', { analysis: 'processed', summary: 'Again.' }),
      ]),
    );
    const user = userEvent.setup();
    render();
    await screen.findByRole('link', { name: 'Post b' });

    await user.click(screen.getByRole('checkbox', { name: 'Hide posts already collected' }));

    expect(screen.queryByRole('link', { name: 'Post b' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Post a' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Post c' })).toBeInTheDocument();
  });

  it('says when entries were left out of the log', async () => {
    vi.mocked(fetchRun).mockResolvedValue(detail(run('r2', { entries_found: 900 }), [ANALYZED]));
    render();

    expect(await screen.findByText(/Showing 1 of 900 entries/)).toBeInTheDocument();
  });

  it('says when there is no run yet', async () => {
    vi.mocked(fetchRuns).mockResolvedValue([]);
    render();

    expect(await screen.findByText(/No collection yet/)).toBeInTheDocument();
  });
});

// --- Refresh ---

describe('Refresh now', () => {
  it('starts a run, opens it and follows it until it finishes', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const fresh = run('r3', { trigger: 'manual', finished_at: null, outcome: null });
    vi.mocked(refreshSource).mockResolvedValue(fresh);
    let polls = 0;
    vi.mocked(fetchRun).mockImplementation(async (_s, id) => {
      if (id !== 'r3') return detail(run(id), [ANALYZED]);
      polls += 1;
      if (polls === 1) return detail(fresh, []);
      if (polls === 2) {
        return detail({ ...fresh, outcome: 'collected' }, [entry('n', { verdict: 'new' })]);
      }
      return detail({ ...fresh, outcome: 'collected', finished_at: '2026-10-03T00:00:00Z' }, [
        entry('n', { verdict: 'new', analysis: 'processed', summary: 'Done now.' }),
      ]);
    });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { router } = render();

    await user.click(await screen.findByRole('button', { name: 'Refresh now' }));

    expect(refreshSource).toHaveBeenCalledWith('s1');
    await waitFor(() => expect(router.state.location.search).toBe('?run=r3'));
    expect(await screen.findByRole('heading', { name: /Reading the source/ })).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS);
    });
    expect(await screen.findByText('Waiting for the model…')).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS);
    });
    expect(await screen.findByText('Done now.')).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS * 3);
    });
    expect(polls).toBe(3);
  });

  it('shows why a refresh could not start', async () => {
    vi.mocked(refreshSource).mockRejectedValue(
      new ApiError(409, 'A collection is already running. Try again in a few minutes.'),
    );
    const user = userEvent.setup();
    render();

    await user.click(await screen.findByRole('button', { name: 'Refresh now' }));

    expect(await screen.findByText(/already running/)).toBeInTheDocument();
  });

  it('is off for a paused blog', async () => {
    vi.mocked(fetchSource).mockResolvedValue({ ...SOURCE, enabled: false });
    render();

    await screen.findByText(/paused/);
    expect(screen.getByRole('button', { name: 'Refresh now' })).toBeDisabled();
  });

  it('is off while a run is going', async () => {
    vi.mocked(fetchRuns).mockResolvedValue([run('r2', { finished_at: null })]);
    render();

    expect(await screen.findByRole('button', { name: 'Collecting…' })).toBeDisabled();
  });
});
