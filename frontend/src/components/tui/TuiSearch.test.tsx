import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Layout from '../Layout';
import { renderWithProviders } from '../../test/renderWithProviders';
import { fetchNotebooks } from '../../api/notebooks';
import { fetchNotes } from '../../api/notes';
import { searchNotes } from '../../api/search';
import type { Note, SearchResponse, SearchResult } from '../../types';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { uid: 'u1', firstname: 'Test', lastname: 'User', invite_quota_remaining: 3 },
    logout: vi.fn(),
  }),
}));

vi.mock('../../api/invites', () => ({
  fetchInvitesConfig: vi.fn().mockResolvedValue({
    registration_enabled: true,
    invites_enabled: false,
  }),
}));

function note(id: string, title: string): Note {
  return {
    id,
    notebook_id: 'nb-1',
    owner_id: 'u1',
    title,
    creation_timestamp: '2026-05-11T10:00:00Z',
    update_timestamp: '2026-05-11T10:00:00Z',
    permissions: ['update'],
    tags: [{ id: 't1', name: 'travel' }],
    preview: '',
  };
}

vi.mock('../../api/notebooks', () => ({
  fetchNotebooks: vi.fn(),
  fetchNotebook: vi.fn((id: string) =>
    Promise.resolve({ id, name: 'Work', owner_id: 'u1', permissions: [] }),
  ),
  createNotebook: vi.fn(),
  deleteNotebook: vi.fn(),
}));

vi.mock('../../api/notes', () => ({
  fetchNotes: vi.fn(),
  fetchNote: vi.fn((_nb: string, id: string) => Promise.resolve(note(id, `Note ${id}`))),
  createNote: vi.fn(),
  deleteNote: vi.fn(),
}));

vi.mock('../../api/search', () => ({ searchNotes: vi.fn(), SEARCH_PAGE_SIZE: 20 }));

vi.mock('../NoteEditor', () => ({
  default: () => (
    <div data-testid="editor" contentEditable="true" suppressContentEditableWarning>
      body
    </div>
  ),
}));

const routes = [
  { path: '/notebooks', element: <Layout /> },
  { path: '/notebooks/:notebookId/notes', element: <Layout /> },
  { path: '/notebooks/:notebookId/notes/:noteId', element: <Layout /> },
];

function result(id: string, title: string, nodeId: string): SearchResult {
  return {
    note: { ...note(id, title), notebook_id: 'nb-2' },
    notebook: { id: 'nb-2', name: 'Travel' },
    score: 1,
    title: [{ text: title, highlighted: true }],
    snippets: [
      {
        node_id: nodeId,
        segments: [
          { text: 'Fly to ', highlighted: false },
          { text: 'Berlin', highlighted: true },
        ],
      },
    ],
  };
}

function page(results: SearchResult[], unknown_tags: string[] = []): SearchResponse {
  return { results, unknown_tags, offset: 0, limit: 20 };
}

function renderTui(url = '/notebooks/nb-1/notes') {
  return renderWithProviders(null, { routes, initialEntries: [url], layout: 'tui' });
}

async function openSearch() {
  const user = userEvent.setup();
  const view = renderTui();
  const notes = await screen.findByRole('listbox', { name: 'Notes' });
  await waitFor(() => expect(notes).toHaveFocus());
  await user.keyboard('/');
  const dialog = await screen.findByRole('dialog', { name: 'Search' });
  return { user, dialog, notes, ...view };
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(fetchNotebooks).mockResolvedValue([
    { id: 'nb-1', name: 'Work', owner_id: 'u1', permissions: [] },
  ]);
  vi.mocked(fetchNotes).mockResolvedValue([note('n-1', 'Groceries')]);
  vi.mocked(searchNotes).mockResolvedValue(
    page([result('n-7', 'Berlin trip', 'node-7'), result('n-8', 'Berlin wall', 'node-8')]),
  );
});

describe('TUI search window', () => {
  it('opens with / and focuses the query field', async () => {
    const { dialog } = await openSearch();

    expect(within(dialog).getByRole('textbox', { name: 'Find' })).toHaveFocus();
    expect(within(dialog).getByText(/tag:name/)).toBeInTheDocument();
  });

  it('opens from File → Search notes', async () => {
    const user = userEvent.setup();
    renderTui();

    await user.click(await screen.findByRole('button', { name: 'File' }));
    await user.click(screen.getByRole('menuitem', { name: /search notes/i }));

    expect(await screen.findByRole('dialog', { name: 'Search' })).toBeInTheDocument();
  });

  it('searches as you type and lists highlighted results', async () => {
    const { user, dialog } = await openSearch();

    await user.keyboard('berl');

    const results = await within(dialog).findByRole('listbox', { name: 'Search results' });
    await within(results).findByText('Berlin trip');
    expect(searchNotes).toHaveBeenLastCalledWith('berl', { offset: 0, limit: 20 });
    const [first] = within(results).getAllByRole('option');
    expect(first).toHaveAttribute('aria-selected', 'true');
    expect(within(first).getByText('Travel')).toBeInTheDocument();
    expect([...first.querySelectorAll('mark')].map((m) => m.textContent)).toEqual([
      'Berlin trip',
      'Berlin',
    ]);
  });

  it('moves the cursor with the arrows and opens the note at the match with Enter', async () => {
    const { user, dialog, router } = await openSearch();
    await user.keyboard('berl');
    await within(dialog).findByText('Berlin wall');

    await user.keyboard('{ArrowDown}');
    expect(within(dialog).getAllByRole('option')[1]).toHaveAttribute('aria-selected', 'true');
    await user.keyboard('{Enter}');

    await waitFor(() =>
      expect(router.state.location.pathname).toBe('/notebooks/nb-2/notes/n-8'),
    );
    expect(router.state.location.search).toBe('?node=node-8');
    expect(screen.queryByRole('dialog', { name: 'Search' })).not.toBeInTheDocument();
  });

  it('closes with Esc and gives focus back to the pane', async () => {
    const { user, notes } = await openSearch();

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('dialog', { name: 'Search' })).not.toBeInTheDocument();
    await waitFor(() => expect(notes).toHaveFocus());
  });

  it('remembers the last query when reopened', async () => {
    const { user } = await openSearch();
    await user.keyboard('berl');
    await user.keyboard('{Escape}');

    await user.keyboard('/');

    const dialog = await screen.findByRole('dialog', { name: 'Search' });
    expect(within(dialog).getByRole('textbox', { name: 'Find' })).toHaveValue('berl');
    expect(await within(dialog).findByText('Berlin trip')).toBeInTheDocument();
  });

  it('says when nothing matches and names unknown tags', async () => {
    vi.mocked(searchNotes).mockResolvedValue(page([], ['work']));
    const { user, dialog } = await openSearch();

    await user.keyboard('tag:work');

    expect(await within(dialog).findByText(/no tag “work”/)).toBeInTheDocument();
  });
});
