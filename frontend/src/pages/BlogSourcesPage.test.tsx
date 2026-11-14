import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BlogSourcesPage from './BlogSourcesPage';
import { ApiError } from '../api/client';
import { renderWithProviders } from '../test/renderWithProviders';
import type { BlogSource } from '../types';

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

vi.mock('../api/categories', () => ({
  CATEGORIES_KEY: ['categories'],
  fetchCategories: vi.fn(),
  createCategory: vi.fn(),
  updateCategory: vi.fn(),
  deleteCategory: vi.fn(),
}));

vi.mock('../api/blogs', () => ({
  fetchSources: vi.fn(),
  fetchSource: vi.fn(),
  createSource: vi.fn(),
  updateSource: vi.fn(),
  deleteSource: vi.fn(),
}));

import { createSource, deleteSource, fetchSource, fetchSources, updateSource } from '../api/blogs';
import { fetchCategories } from '../api/categories';

function source(fields: Partial<BlogSource> = {}): BlogSource {
  return {
    id: 's1',
    category_id: null,
    url: 'https://blog.example.com',
    feed_url: 'https://blog.example.com/feed.xml',
    kind: 'feed',
    title: 'Example Blog',
    remarks: null,
    preferences: 'Databases',
    collect_since: '2026-10-01T00:00:00Z',
    enabled: true,
    archived_at: null,
    last_fetched_at: '2026-10-02T00:00:00Z',
    last_error: null,
    consecutive_failures: 0,
    created_at: '2026-10-01T00:00:00Z',
    useful_post_count: null,
    ...fields,
  };
}

function render() {
  return renderWithProviders(<BlogSourcesPage />, { initialEntries: ['/blogs/sources'] });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchCategories).mockResolvedValue([
    { id: 'd1', name: 'Tech', description: null, created_at: '2026-10-01T00:00:00Z' },
  ]);
  vi.mocked(fetchSources).mockResolvedValue([source()]);
  vi.mocked(fetchSource).mockResolvedValue(source({ useful_post_count: 3 }));
  vi.mocked(createSource).mockResolvedValue(source());
  vi.mocked(updateSource).mockResolvedValue(source());
  vi.mocked(deleteSource).mockResolvedValue(undefined);
});

// --- Status ---

describe('source status', () => {
  it('says a new source waits for the first collection', async () => {
    vi.mocked(fetchSources).mockResolvedValue([source({ last_fetched_at: null })]);
    render();
    expect(await screen.findByText('Waiting for first collection')).toBeInTheDocument();
  });

  it('shows the last error of a failing source', async () => {
    vi.mocked(fetchSources).mockResolvedValue([
      source({ last_error: 'The server answered HTTP 500' }),
    ]);
    render();
    expect(await screen.findByText('The server answered HTTP 500')).toBeInTheDocument();
  });

  it('says a source is paused', async () => {
    vi.mocked(fetchSources).mockResolvedValue([source({ enabled: false })]);
    render();
    expect(await screen.findByText('Paused')).toBeInTheDocument();
  });

  it('says when a source was last collected', async () => {
    render();
    expect(await screen.findByText(/Last collected/)).toBeInTheDocument();
  });
});

// --- Adding ---

describe('history', () => {
  it('links each source to its collection history', async () => {
    render();

    expect(await screen.findByRole('link', { name: 'History of Example Blog' })).toHaveAttribute(
      'href',
      '/blogs/sources/s1/log',
    );
  });
});

describe('adding a source', () => {
  it('sends the form and warns about the look back', async () => {
    const user = userEvent.setup();
    render();

    await user.click(await screen.findByRole('button', { name: 'Add a blog' }));
    expect(screen.getByText(/may return fewer posts than expected/)).toBeInTheDocument();

    await user.type(screen.getByLabelText('Blog or feed URL'), 'https://new.example.com');
    await user.type(screen.getByLabelText(/^Preferences/), 'Only compilers');
    await screen.findByRole('option', { name: 'Tech' });
    await user.selectOptions(screen.getByLabelText('Category'), 'Tech');
    await user.click(screen.getByRole('button', { name: 'Add blog' }));

    await waitFor(() =>
      expect(createSource).toHaveBeenCalledWith({
        url: 'https://new.example.com',
        title: undefined,
        remarks: '',
        preferences: 'Only compilers',
        category_id: 'd1',
        lookback_days: 7,
      }),
    );
  });

  it('shows why a URL was refused', async () => {
    vi.mocked(createSource).mockRejectedValue(new ApiError(422, 'No feed found at this URL'));
    const user = userEvent.setup();
    render();

    await user.click(await screen.findByRole('button', { name: 'Add a blog' }));
    await user.type(screen.getByLabelText('Blog or feed URL'), 'https://nothing.example.com');
    await user.click(screen.getByRole('button', { name: 'Add blog' }));

    expect(await screen.findByText('No feed found at this URL')).toBeInTheDocument();
  });
});

// --- Editing ---

describe('editing a source', () => {
  it('edits fields but not the URL or look back', async () => {
    const user = userEvent.setup();
    render();

    await user.click(await screen.findByRole('button', { name: 'Edit Example Blog' }));
    expect(screen.queryByLabelText('Blog or feed URL')).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Look back/)).not.toBeInTheDocument();
    expect(screen.getByText('Changes apply to new posts only.')).toBeInTheDocument();

    const title = screen.getByLabelText('Title');
    await user.clear(title);
    await user.type(title, 'Renamed');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(updateSource).toHaveBeenCalledWith('s1', {
        title: 'Renamed',
        remarks: '',
        preferences: 'Databases',
        category_id: null,
      }),
    );
  });

  it('pauses and resumes', async () => {
    const user = userEvent.setup();
    render();

    await user.click(await screen.findByRole('button', { name: 'Pause Example Blog' }));

    await waitFor(() => expect(updateSource).toHaveBeenCalledWith('s1', { enabled: false }));
  });
});

// --- Deleting ---

describe('deleting a source', () => {
  async function openDialog() {
    const user = userEvent.setup();
    render();
    await user.click(await screen.findByRole('button', { name: 'Delete Example Blog' }));
    const dialog = screen.getByRole('alertdialog');
    return { user, dialog };
  }

  it('shows the number of useful posts', async () => {
    const { dialog } = await openDialog();
    expect(await within(dialog).findByText(/It has 3 useful posts/)).toBeInTheDocument();
  });

  it('can delete everything', async () => {
    const { user, dialog } = await openDialog();
    await within(dialog).findByText(/It has 3 useful posts/);
    await user.click(within(dialog).getByRole('button', { name: 'Delete everything' }));
    await waitFor(() => expect(deleteSource).toHaveBeenCalledWith('s1', false));
  });

  it('can keep the useful posts', async () => {
    const { user, dialog } = await openDialog();
    await within(dialog).findByText(/It has 3 useful posts/);
    await user.click(within(dialog).getByRole('button', { name: 'Keep useful posts' }));
    await waitFor(() => expect(deleteSource).toHaveBeenCalledWith('s1', true));
  });

  it('has nothing to keep without useful posts', async () => {
    vi.mocked(fetchSource).mockResolvedValue(source({ useful_post_count: 0 }));
    const { dialog } = await openDialog();
    await within(dialog).findByText(/It has 0 useful posts/);
    expect(within(dialog).getByRole('button', { name: 'Keep useful posts' })).toBeDisabled();
  });

  it('can be cancelled', async () => {
    const { user, dialog } = await openDialog();
    await user.click(within(dialog).getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(deleteSource).not.toHaveBeenCalled();
  });
});

// --- Categories ---

describe('categories', () => {
  it('opens Manage categories', async () => {
    const user = userEvent.setup();
    render();

    await user.click(await screen.findByRole('button', { name: 'Manage categories' }));
    const dialog = screen.getByRole('dialog', { name: 'Manage categories' });
    expect(await within(dialog).findByText('Tech')).toBeInTheDocument();
    await user.click(within(dialog).getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

// --- Mobile ---

describe('mobile layout', () => {
  it('goes back to the posts', async () => {
    renderWithProviders(<BlogSourcesPage />, {
      initialEntries: ['/blogs/sources'],
      layout: 'mobile',
    });

    expect(await screen.findByRole('link', { name: 'Back' })).toHaveAttribute('href', '/blogs');
  });
});
