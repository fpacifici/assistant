import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BlogsPage from './BlogsPage';
import { renderWithProviders } from '../test/renderWithProviders';
import { mockIntersectionObserver, scrollIntoView } from '../test/intersectionObserver';
import { UNDO_MS } from '../components/blogs/PostList';
import type { BlogPost, BlogSource } from '../types';

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

vi.mock('../api/tags', () => ({ fetchTags: vi.fn() }));

vi.mock('../api/blogs', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/blogs')>()),
  fetchDirectories: vi.fn(),
  fetchSources: vi.fn(),
  fetchPosts: vi.fn(),
  setPostState: vi.fn(),
  setPostsState: vi.fn(),
  addPostTag: vi.fn(),
  removePostTag: vi.fn(),
}));

import {
  addPostTag,
  fetchDirectories,
  fetchPosts,
  fetchSources,
  removePostTag,
  setPostsState,
  setPostState,
} from '../api/blogs';
import { fetchTags } from '../api/tags';

function post(id: string, fields: Partial<BlogPost> = {}): BlogPost {
  return {
    id,
    source_id: 's1',
    source_title: 'Example Blog',
    url: `https://blog.example.com/${id}`,
    title: `Post ${id}`,
    published_at: '2026-10-01T12:00:00Z',
    summary: `Summary of ${id}`,
    match_level: null,
    motivation: null,
    status: 'processed',
    state: 'new',
    evaluated_at: null,
    tags: [],
    ...fields,
  };
}

function archivedSource(id: string, title: string): BlogSource {
  return { id, title, archived_at: '2026-10-01T00:00:00Z' } as BlogSource;
}

function showPosts(...posts: BlogPost[]) {
  vi.mocked(fetchPosts).mockResolvedValue({ posts, next_cursor: null });
}

const WORK = { id: 't1', name: 'Work' };

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchDirectories).mockResolvedValue([
    { id: 'd1', name: 'Tech', created_at: '2026-10-01T00:00:00Z' },
  ]);
  vi.mocked(fetchSources).mockResolvedValue([]);
  vi.mocked(fetchTags).mockResolvedValue([WORK]);
  vi.mocked(setPostState).mockImplementation(async (id, state) => post(id, { state }));
  vi.mocked(setPostsState).mockResolvedValue({ updated: 1 });
  showPosts();
});

afterEach(() => {
  vi.useRealTimers();
});

// --- Views ---

describe('BlogsPage views', () => {
  it('asks for every post on All, newest first from the server', async () => {
    showPosts(post('a'), post('b'));
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    expect(await screen.findByRole('link', { name: 'Post a' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Post b' })).toBeInTheDocument();
    expect(fetchPosts).toHaveBeenCalledWith('all', {}, undefined);
    expect(screen.getByRole('link', { name: 'All' })).toHaveAttribute('aria-current', 'page');
  });

  it('asks for useful posts on Relevant', async () => {
    renderWithProviders(<BlogsPage view="relevant" />, { initialEntries: ['/blogs/relevant'] });

    expect(await screen.findByText(/mark as useful appear here/i)).toBeInTheDocument();
    expect(fetchPosts).toHaveBeenCalledWith('relevant', {}, undefined);
  });

  it('asks for new posts on New, with no tag filter', async () => {
    renderWithProviders(<BlogsPage view="new" />, { initialEntries: ['/blogs/review?tag=t1'] });

    expect(await screen.findByText('Nothing new to review.')).toBeInTheDocument();
    expect(fetchPosts).toHaveBeenCalledWith('new', {}, undefined);
    expect(screen.queryByLabelText('Filter by tag')).not.toBeInTheDocument();
  });

  it('keeps the directory when switching view', async () => {
    const { router } = renderWithProviders(<BlogsPage view="all" />, {
      initialEntries: ['/blogs?directory=d1'],
    });
    const user = userEvent.setup();

    await user.click(await screen.findByRole('link', { name: 'Relevant' }));

    expect(router.state.location.pathname).toBe('/blogs/relevant');
    expect(router.state.location.search).toBe('?directory=d1');
  });

  it('shows an error when posts cannot be loaded', async () => {
    vi.mocked(fetchPosts).mockRejectedValue(new Error('boom'));
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    expect(await screen.findByText('Could not load the posts.')).toBeInTheDocument();
  });
});

// --- Filters ---

describe('BlogsPage filters', () => {
  it('filters by directory from the sidebar', async () => {
    const user = userEvent.setup();
    const { router } = renderWithProviders(<BlogsPage view="all" />, {
      initialEntries: ['/blogs'],
    });

    await user.click(await screen.findByRole('link', { name: 'Tech' }));

    expect(router.state.location.search).toBe('?directory=d1');
    await waitFor(() =>
      expect(fetchPosts).toHaveBeenCalledWith('all', { directoryId: 'd1' }, undefined),
    );
  });

  it('offers Unfiled', async () => {
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    await user.click(await screen.findByRole('link', { name: 'Unfiled' }));

    await waitFor(() => expect(fetchPosts).toHaveBeenCalledWith('all', { unfiled: true }, undefined));
  });

  it('filters by tag', async () => {
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="relevant" />, { initialEntries: ['/blogs/relevant'] });

    await screen.findByRole('option', { name: 'Work' });
    await user.selectOptions(screen.getByLabelText('Filter by tag'), 'Work');

    await waitFor(() =>
      expect(fetchPosts).toHaveBeenCalledWith('relevant', { tagId: 't1' }, undefined),
    );
  });

  it('offers archived sources that still have useful posts', async () => {
    vi.mocked(fetchSources).mockResolvedValue([archivedSource('s9', 'Old Blog')]);
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    await user.click(await screen.findByRole('link', { name: 'Old Blog' }));

    expect(fetchSources).toHaveBeenCalledWith({ archived: true });
    await waitFor(() =>
      expect(fetchPosts).toHaveBeenCalledWith('all', { sourceId: 's9' }, undefined),
    );
  });
});

// --- Cards ---

describe('PostCard', () => {
  it('shows everything a card has', async () => {
    showPosts(
      post('a', { match_level: 'high', motivation: 'It is about databases.', tags: [WORK] }),
    );
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    const card = (await screen.findByRole('link', { name: 'Post a' })).closest('li')!;
    expect(within(card).getByText('Example Blog')).toBeInTheDocument();
    expect(within(card).getByText('Summary of a')).toBeInTheDocument();
    expect(within(card).getByText('high match')).toBeInTheDocument();
    expect(within(card).getByText('It is about databases.')).toBeInTheDocument();
    expect(within(card).getByText('Work')).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Useful' })).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'Not useful' })).toBeInTheDocument();
  });

  it('opens the original post in a new tab, safely', async () => {
    showPosts(post('a'));
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    const link = await screen.findByRole('link', { name: 'Post a' });
    expect(link).toHaveAttribute('href', 'https://blog.example.com/a');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it.each(['javascript:alert(1)', 'data:text/html,x', 'not a url'])(
    'does not link to %s',
    async (url) => {
      showPosts(post('a', { url }));
      renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

      expect(await screen.findByText('Post a')).toBeInTheDocument();
      expect(screen.queryByRole('link', { name: 'Post a' })).not.toBeInTheDocument();
    },
  );

  it('shows a failed post with its title, link and no summary', async () => {
    showPosts(post('a', { status: 'failed', summary: null }));
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    expect(await screen.findByRole('link', { name: 'Post a' })).toBeInTheDocument();
    expect(screen.getByText('Summary unavailable')).toBeInTheDocument();
  });

  it('falls back to the URL for a failed post with no title', async () => {
    showPosts(post('a', { status: 'failed', summary: null, title: null }));
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    expect(
      await screen.findByRole('link', { name: 'https://blog.example.com/a' }),
    ).toBeInTheDocument();
  });

  it('renders model output as text, never as HTML', async () => {
    showPosts(post('a', { summary: '<img src=x onerror=alert(1)>' }));
    const { container } = renderWithProviders(<BlogsPage view="all" />, {
      initialEntries: ['/blogs'],
    });

    expect(await screen.findByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
  });

  it('adds a tag by name and shows it', async () => {
    vi.mocked(addPostTag).mockResolvedValue([{ id: 't2', name: 'Fresh' }]);
    showPosts(post('a'));
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    await user.type(await screen.findByRole('combobox', { name: 'Add tag' }), 'Fresh{Enter}');

    await waitFor(() => expect(addPostTag).toHaveBeenCalledWith('a', { name: 'Fresh' }));
    expect(await screen.findByText('Fresh')).toBeInTheDocument();
  });

  it('removes a tag', async () => {
    vi.mocked(removePostTag).mockResolvedValue(undefined);
    showPosts(post('a', { tags: [WORK] }));
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    await user.click(await screen.findByRole('button', { name: 'Remove tag Work' }));

    await waitFor(() => expect(removePostTag).toHaveBeenCalledWith('a', 't1'));
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Remove tag Work' })).not.toBeInTheDocument(),
    );
  });
});

// --- Verdicts ---

describe('verdicts', () => {
  it('removes an evaluated post from New right away', async () => {
    let resolve: (value: BlogPost) => void = () => {};
    vi.mocked(setPostState).mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );
    showPosts(post('a'), post('b'));
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="new" />, { initialEntries: ['/blogs/review'] });

    const card = (await screen.findByRole('link', { name: 'Post a' })).closest('li')!;
    await user.click(within(card).getByRole('button', { name: 'Useful' }));

    // Still in flight, and already gone.
    expect(screen.queryByRole('link', { name: 'Post a' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Post b' })).toBeInTheDocument();
    expect(setPostState).toHaveBeenCalledWith('a', 'useful');
    resolve(post('a', { state: 'useful' }));
  });

  it('undoes a verdict', async () => {
    showPosts(post('a'));
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="new" />, { initialEntries: ['/blogs/review'] });

    const card = (await screen.findByRole('link', { name: 'Post a' })).closest('li')!;
    await user.click(within(card).getByRole('button', { name: 'Not useful' }));
    expect(await screen.findByText('Marked not useful: Post a')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Undo' }));

    await waitFor(() => expect(setPostState).toHaveBeenLastCalledWith('a', 'new'));
    expect(await screen.findByRole('link', { name: 'Post a' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument();
  });

  it('drops the undo after a few seconds', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    showPosts(post('a'));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderWithProviders(<BlogsPage view="new" />, { initialEntries: ['/blogs/review'] });

    const card = (await screen.findByRole('link', { name: 'Post a' })).closest('li')!;
    await user.click(within(card).getByRole('button', { name: 'Useful' }));
    expect(await screen.findByRole('button', { name: 'Undo' })).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(UNDO_MS);
    });

    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument();
  });

  it('puts the post back when saving fails', async () => {
    vi.mocked(setPostState).mockRejectedValue(new Error('boom'));
    showPosts(post('a'));
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="new" />, { initialEntries: ['/blogs/review'] });

    const card = (await screen.findByRole('link', { name: 'Post a' })).closest('li')!;
    await user.click(within(card).getByRole('button', { name: 'Useful' }));

    expect(await screen.findByText('Could not save that. Please try again.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Post a' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument();
  });

  it('keeps a post on All and shows its verdict', async () => {
    showPosts(post('a'));
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    await user.click(await screen.findByRole('button', { name: 'Useful' }));

    expect(screen.getByRole('link', { name: 'Post a' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Useful' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument();
  });

  it('pressing the current verdict again takes it back', async () => {
    showPosts(post('a', { state: 'useful' }));
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    await user.click(await screen.findByRole('button', { name: 'Useful' }));

    await waitFor(() => expect(setPostState).toHaveBeenCalledWith('a', 'new'));
  });

  it('removes a post from Relevant when it stops being useful', async () => {
    showPosts(post('a', { state: 'useful' }));
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="relevant" />, { initialEntries: ['/blogs/relevant'] });

    await user.click(await screen.findByRole('button', { name: 'Not useful' }));

    expect(screen.queryByRole('link', { name: 'Post a' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Undo' })).toBeInTheDocument();
  });

  it('opening a post changes nothing', async () => {
    showPosts(post('a'));
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="new" />, { initialEntries: ['/blogs/review'] });

    await user.click(await screen.findByRole('link', { name: 'Post a' }));

    expect(setPostState).not.toHaveBeenCalled();
  });
});

// --- Bulk ---

describe('Mark visible as not useful', () => {
  it('is only offered on New', async () => {
    showPosts(post('a'));
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'] });

    await screen.findByRole('link', { name: 'Post a' });
    expect(
      screen.queryByRole('button', { name: 'Mark visible as not useful' }),
    ).not.toBeInTheDocument();
  });

  it('asks first, and sends the ids on screen', async () => {
    showPosts(post('a'), post('b'));
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="new" />, { initialEntries: ['/blogs/review?directory=d1'] });

    await user.click(await screen.findByRole('button', { name: 'Mark visible as not useful' }));
    expect(setPostsState).not.toHaveBeenCalled();

    const dialog = screen.getByRole('alertdialog');
    expect(within(dialog).getByText('Mark the 2 visible posts as not useful?')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Mark as not useful' }));

    await waitFor(() => expect(setPostsState).toHaveBeenCalledWith(['a', 'b'], 'not_useful'));
  });

  it('does nothing when cancelled', async () => {
    showPosts(post('a'));
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="new" />, { initialEntries: ['/blogs/review'] });

    await user.click(await screen.findByRole('button', { name: 'Mark visible as not useful' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Cancel' }));

    expect(setPostsState).not.toHaveBeenCalled();
  });
});

// --- Scrolling ---

describe('infinite scroll', () => {
  it('loads the next page with the cursor', async () => {
    vi.mocked(fetchPosts)
      .mockResolvedValueOnce({ posts: [post('a')], next_cursor: 'next' })
      .mockResolvedValueOnce({ posts: [post('b')], next_cursor: null });
    mockIntersectionObserver();
    const { container } = renderWithProviders(<BlogsPage view="all" />, {
      initialEntries: ['/blogs'],
    });

    await screen.findByRole('link', { name: 'Post a' });
    scrollIntoView(container.querySelector('.blog-posts + [aria-hidden="true"]')!);

    expect(await screen.findByRole('link', { name: 'Post b' })).toBeInTheDocument();
    expect(fetchPosts).toHaveBeenLastCalledWith('all', {}, 'next');
  });
});

// --- Mobile ---

describe('mobile layout', () => {
  it('shows the directories first, not the posts', async () => {
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'], layout: 'mobile' });

    expect(await screen.findByRole('link', { name: 'Tech' })).toBeInTheDocument();
    expect(fetchPosts).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'Back' })).toHaveAttribute('href', '/notebooks');
  });

  it('shows the posts alone once a directory is chosen', async () => {
    showPosts(post('a'));
    renderWithProviders(<BlogsPage view="all" />, {
      initialEntries: ['/blogs?directory=d1'],
      layout: 'mobile',
    });

    expect(await screen.findByRole('link', { name: 'Post a' })).toBeInTheDocument();
    expect(screen.queryByRole('navigation', { name: 'Directories' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back' })).toHaveAttribute('href', '/blogs');
  });

  it('reaches every post from All directories', async () => {
    const user = userEvent.setup();
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'], layout: 'mobile' });

    await user.click(await screen.findByRole('link', { name: 'All directories' }));

    await waitFor(() => expect(fetchPosts).toHaveBeenCalledWith('all', {}, undefined));
  });
});

// --- TUI ---

describe('TUI layout', () => {
  it('shows the desktop page', async () => {
    showPosts(post('a'));
    renderWithProviders(<BlogsPage view="all" />, { initialEntries: ['/blogs'], layout: 'tui' });

    expect(await screen.findByRole('link', { name: 'Post a' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Directories' })).toBeInTheDocument();
  });
});
