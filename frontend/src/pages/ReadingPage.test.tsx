import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ReadingPage from './ReadingPage';
import { ApiError } from '../api/client';
import { MAX_POLL_MS, PENDING_POLL_MS } from '../components/reading/LinkList';
import { readingLink } from '../test/readingLinks';
import { renderWithProviders } from '../test/renderWithProviders';
import type { LinkState } from '../types';

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
vi.mock('../api/ask', () => ({ fetchAskStatus: vi.fn() }));
vi.mock('../api/categories', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/categories')>()),
  fetchCategories: vi.fn(),
}));
vi.mock('../api/reading', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/reading')>()),
  fetchLinks: vi.fn(),
  fetchLinkCounts: vi.fn(),
  fetchLink: vi.fn(),
  addLink: vi.fn(),
}));

import { fetchCategories } from '../api/categories';
import { fetchAskStatus } from '../api/ask';
import { addLink, fetchLink, fetchLinkCounts, fetchLinks } from '../api/reading';

const TECH = { id: 'c1', name: 'Tech', description: null, created_at: '2026-10-01T00:00:00Z' };
const EMPTY_CAT = { id: 'c2', name: 'Cooking', description: null, created_at: '2026-10-01T00:00:00Z' };

function render(path: string, state: LinkState, layout: 'desktop' | 'mobile' = 'desktop') {
  return renderWithProviders(<ReadingPage state={state} />, { initialEntries: [path], layout });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchAskStatus).mockResolvedValue({ enabled: true });
  vi.mocked(fetchCategories).mockResolvedValue([TECH, EMPTY_CAT]);
  vi.mocked(fetchLinkCounts).mockResolvedValue([
    { category_id: 'c1', count: 2 },
    { category_id: null, count: 1 },
  ]);
  vi.mocked(fetchLinks).mockImplementation(async (_state, filter) => ({
    links:
      'unfiled' in filter
        ? [readingLink({ id: 'u1', title: 'Loose link' })]
        : [readingLink({ id: 'a', title: 'First' }), readingLink({ id: 'b', title: 'Second' })],
    next_cursor: null,
  }));
});

afterEach(() => {
  vi.useRealTimers();
});

// --- To read ---

describe('to read', () => {
  it('shows one section per category with links, then Unfiled', async () => {
    render('/reading', 'to_read');
    const tech = await screen.findByRole('region', { name: 'Tech' });
    expect(within(tech).getByRole('button', { name: /Tech\s*2/ })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(await within(tech).findByText('First')).toBeInTheDocument();
    const unfiled = screen.getByRole('region', { name: 'Unfiled' });
    expect(await within(unfiled).findByText('Loose link')).toBeInTheDocument();
    expect(screen.queryByRole('region', { name: 'Cooking' })).not.toBeInTheDocument();
    expect(fetchLinks).toHaveBeenCalledWith('to_read', { categoryId: 'c1' }, undefined);
    expect(fetchLinks).toHaveBeenCalledWith('to_read', { unfiled: true }, undefined);
  });

  it('folds a section', async () => {
    const user = userEvent.setup();
    render('/reading', 'to_read');
    const tech = await screen.findByRole('region', { name: 'Tech' });
    await within(tech).findByText('First');
    await user.click(within(tech).getByRole('button', { name: /Tech/ }));
    expect(within(tech).queryByText('First')).not.toBeInTheDocument();
  });

  it('says when there is nothing to read', async () => {
    vi.mocked(fetchLinkCounts).mockResolvedValue([]);
    render('/reading', 'to_read');
    expect(await screen.findByText(/Nothing to read/)).toBeInTheDocument();
  });

  it('narrows to one category from the sidebar', async () => {
    const user = userEvent.setup();
    const { router } = render('/reading', 'to_read');
    const sidebar = screen.getByRole('navigation', { name: 'Categories' });
    await user.click(await within(sidebar).findByRole('link', { name: /Tech/ }));
    expect(router.state.location.search).toBe('?category=c1');
    expect(screen.queryByRole('region', { name: 'Unfiled' })).not.toBeInTheDocument();
    expect(within(sidebar).getByRole('link', { name: /Unfiled\s*1/ })).toBeInTheDocument();
    expect(within(sidebar).getByRole('link', { name: /All categories\s*3/ })).toBeInTheDocument();
  });
});

// --- Adding ---

describe('adding a link', () => {
  it('adds a link and refreshes the list', async () => {
    vi.mocked(addLink).mockResolvedValue(readingLink({ analysis_status: 'pending' }));
    const user = userEvent.setup();
    render('/reading', 'to_read');
    await screen.findByRole('region', { name: 'Tech' });
    const calls = vi.mocked(fetchLinkCounts).mock.calls.length;
    await user.type(screen.getByLabelText('Link to add'), 'https://new.example.com/a');
    await user.click(screen.getByRole('button', { name: 'Add link' }));
    await waitFor(() => expect(addLink).toHaveBeenCalledWith('https://new.example.com/a'));
    await waitFor(() => expect(vi.mocked(fetchLinkCounts).mock.calls.length).toBeGreaterThan(calls));
    expect(screen.getByLabelText('Link to add')).toHaveValue('');
  });

  it('points to the link already saved', async () => {
    vi.mocked(addLink).mockRejectedValue(
      new ApiError(409, 'This link is already in your reading list', { link_id: 'a' }),
    );
    vi.mocked(fetchLink).mockResolvedValue(
      readingLink({ id: 'a', title: 'Saved before', state: 'discarded', category_id: 'c1' }),
    );
    const user = userEvent.setup();
    const { router } = render('/reading', 'to_read');
    await user.type(screen.getByLabelText('Link to add'), 'https://example.com/btrees');
    await user.click(screen.getByRole('button', { name: 'Add link' }));
    expect(await screen.findByText(/already in your reading list/)).toBeInTheDocument();
    expect(fetchLink).toHaveBeenCalledWith('a');
    await user.click(screen.getByRole('link', { name: 'Saved before' }));
    expect(router.state.location.pathname).toBe('/reading/archive');
    expect(router.state.location.search).toBe('?category=c1');
    expect(router.state.location.hash).toBe('#link-a');
  });

  it('shows other errors as they are', async () => {
    vi.mocked(addLink).mockRejectedValue(new ApiError(422, 'Enter an http or https URL'));
    const user = userEvent.setup();
    render('/reading', 'to_read');
    await user.type(screen.getByLabelText('Link to add'), 'https://x');
    await user.click(screen.getByRole('button', { name: 'Add link' }));
    expect(await screen.findByText('Enter an http or https URL')).toBeInTheDocument();
  });

  it('is only in To read', async () => {
    render('/reading/archive', 'discarded');
    await screen.findByText('First');
    expect(screen.queryByLabelText('Link to add')).not.toBeInTheDocument();
  });
});

// --- Polling ---

describe('analysis in progress', () => {
  it('polls while a link is being analyzed, then refreshes the counts', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchLinkCounts).mockResolvedValue([{ category_id: null, count: 1 }]);
    vi.mocked(fetchLinks)
      .mockResolvedValueOnce({
        links: [readingLink({ id: 'p', title: null, analysis_status: 'pending', summary: null })],
        next_cursor: null,
      })
      .mockResolvedValue({
        links: [readingLink({ id: 'p', title: 'Analyzed' })],
        next_cursor: null,
      });
    render('/reading', 'to_read');
    expect(await screen.findByText('Analyzing…')).toBeInTheDocument();
    const counts = vi.mocked(fetchLinkCounts).mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PENDING_POLL_MS + 100);
    });
    expect(await screen.findByText('Analyzed')).toBeInTheDocument();
    await waitFor(() => expect(vi.mocked(fetchLinkCounts).mock.calls.length).toBeGreaterThan(counts));
  });

  it('does not poll when AI is off', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchAskStatus).mockResolvedValue({ enabled: false });
    vi.mocked(fetchLinkCounts).mockResolvedValue([{ category_id: null, count: 1 }]);
    vi.mocked(fetchLinks).mockResolvedValue({
      links: [readingLink({ id: 'p', analysis_status: 'pending', summary: null })],
      next_cursor: null,
    });
    render('/reading', 'to_read');
    expect(await screen.findByText('Waiting for analysis')).toBeInTheDocument();
    const calls = vi.mocked(fetchLinks).mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PENDING_POLL_MS * 3);
    });
    expect(vi.mocked(fetchLinks).mock.calls.length).toBe(calls);
  });

  it('stops polling when nothing changes for a while', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.mocked(fetchLinkCounts).mockResolvedValue([{ category_id: null, count: 1 }]);
    vi.mocked(fetchLinks).mockResolvedValue({
      links: [readingLink({ id: 'p', analysis_status: 'pending', summary: null })],
      next_cursor: null,
    });
    render('/reading', 'to_read');
    expect(await screen.findByText('Analyzing…')).toBeInTheDocument();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MAX_POLL_MS + PENDING_POLL_MS);
    });
    const calls = vi.mocked(fetchLinks).mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(PENDING_POLL_MS * 3);
    });
    expect(vi.mocked(fetchLinks).mock.calls.length).toBe(calls);
  });
});

// --- Archive and Promoted ---

describe('other views', () => {
  it('archive is one list of discarded links', async () => {
    render('/reading/archive', 'discarded');
    expect(await screen.findByText('First')).toBeInTheDocument();
    expect(fetchLinks).toHaveBeenCalledWith('discarded', {}, undefined);
    expect(fetchLinkCounts).toHaveBeenCalledWith('discarded');
    expect(screen.queryByRole('region', { name: 'Tech' })).not.toBeInTheDocument();
  });

  it('promoted narrows to Unfiled', async () => {
    render('/reading/promoted?category=unfiled', 'promoted');
    expect(await screen.findByText('Loose link')).toBeInTheDocument();
    expect(fetchLinks).toHaveBeenCalledWith('promoted', { unfiled: true }, undefined);
  });

  it('switching view keeps the category', async () => {
    const user = userEvent.setup();
    const { router } = render('/reading?category=c1', 'to_read');
    const views = screen.getByRole('navigation', { name: 'Reading views' });
    await user.click(within(views).getByRole('link', { name: 'Archive' }));
    expect(router.state.location.pathname).toBe('/reading/archive');
    expect(router.state.location.search).toBe('?category=c1');
  });
});

// --- Header and categories ---

describe('header and categories', () => {
  it('marks Reading as the current section', async () => {
    render('/reading', 'to_read');
    const sections = screen.getByRole('navigation', { name: 'Sections' });
    expect(await within(sections).findByRole('link', { name: 'Reading' })).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('opens Manage categories', async () => {
    const user = userEvent.setup();
    render('/reading', 'to_read');
    await user.click(screen.getByRole('button', { name: 'Manage categories' }));
    expect(screen.getByRole('dialog', { name: 'Manage categories' })).toBeInTheDocument();
  });
});

// --- Mobile ---

describe('mobile layout', () => {
  it('replaces the sidebar with a category picker with counts', async () => {
    const user = userEvent.setup();
    const { router } = render('/reading', 'to_read', 'mobile');
    expect(screen.queryByRole('navigation', { name: 'Categories' })).not.toBeInTheDocument();
    await screen.findByRole('option', { name: 'Tech (2)' });
    expect(screen.getByRole('option', { name: 'Unfiled (1)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'All categories (3)' })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText('Filter by category'), 'Tech (2)');
    expect(router.state.location.search).toBe('?category=c1');
  });

  it('has Manage categories next to the picker', async () => {
    const user = userEvent.setup();
    render('/reading', 'to_read', 'mobile');
    await user.click(screen.getByRole('button', { name: 'Manage categories' }));
    expect(screen.getByRole('dialog', { name: 'Manage categories' })).toBeInTheDocument();
  });
});
