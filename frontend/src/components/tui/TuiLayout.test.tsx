import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Layout from '../Layout';
import { renderWithProviders } from '../../test/renderWithProviders';
import { createNotebook, fetchNotebooks } from '../../api/notebooks';
import { createNote, deleteNote, fetchNotes } from '../../api/notes';
import type { Note, Notebook } from '../../types';

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { uid: 'u1', firstname: 'Test', lastname: 'User', invite_quota_remaining: 3 },
    logout: vi.fn(),
  }),
}));

vi.mock('../../api/invites', () => ({
  fetchInvitesConfig: vi.fn().mockResolvedValue({
    registration_enabled: true,
    invites_enabled: true,
  }),
}));

function notebook(id: string, name: string): Notebook {
  return { id, name, owner_id: 'u1', permissions: ['delete_notebook', 'share_notebook'] };
}

function note(id: string, title: string): Note {
  return {
    id,
    notebook_id: 'nb-1',
    owner_id: 'u1',
    title,
    creation_timestamp: '2026-05-11T10:00:00Z',
    update_timestamp: '2026-05-11T10:00:00Z',
    permissions: ['update', 'delete_note', 'share_note'],
    tags: [{ id: 't1', name: 'work' }],
    preview: `${title} preview`,
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
  fetchNote: vi.fn((_nb: string, id: string) => Promise.resolve({ ...note(id, `Note ${id}`) })),
  createNote: vi.fn(),
  deleteNote: vi.fn(),
}));

// The editor is BlockNote; a plain editable stands in for it.
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

function renderTui(url: string) {
  return renderWithProviders(null, { routes, initialEntries: [url], layout: 'tui' });
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(fetchNotebooks).mockResolvedValue([
    notebook('nb-1', 'Work'),
    notebook('nb-2', 'Home'),
    notebook('nb-3', 'Ideas'),
  ]);
  vi.mocked(fetchNotes).mockResolvedValue([note('n-1', 'Groceries'), note('n-2', 'Plans')]);
});

// --- Rendering ---

describe('TUI layout', () => {
  it('renders the panes, menu bar and key bar', async () => {
    renderTui('/notebooks/nb-1/notes');

    expect(await screen.findByRole('listbox', { name: 'Notebooks' })).toBeInTheDocument();
    expect(await screen.findByRole('listbox', { name: 'Notes' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'File' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'F7 New' })).toBeInTheDocument();
    expect(screen.getAllByText('#work')).toHaveLength(2);
    // The classic header is not shown.
    expect(screen.queryByRole('button', { name: 'Logout' })).not.toBeInTheDocument();
  });

  it('starts the cursor on the open notebook and focuses the notes pane', async () => {
    renderTui('/notebooks/nb-2/notes');

    const notebooks = await screen.findByRole('listbox', { name: 'Notebooks' });
    expect(within(notebooks).getByRole('option', { selected: true })).toHaveTextContent('Home');
    const notes = await screen.findByRole('listbox', { name: 'Notes' });
    await waitFor(() => expect(notes).toHaveFocus());
  });

  // --- Keyboard navigation ---

  it('moves the cursor with arrows and opens with Enter', async () => {
    const user = userEvent.setup();
    const { router } = renderTui('/notebooks');

    const list = await screen.findByRole('listbox', { name: 'Notebooks' });
    await waitFor(() => expect(list).toHaveFocus());
    await screen.findByText('Ideas');

    await user.keyboard('{ArrowDown}{ArrowDown}');
    expect(within(list).getByRole('option', { selected: true })).toHaveTextContent('Ideas');
    await user.keyboard('{ArrowUp}{Enter}');

    expect(router.state.location.pathname).toBe('/notebooks/nb-2/notes');
    const notes = await screen.findByRole('listbox', { name: 'Notes' });
    await waitFor(() => expect(notes).toHaveFocus());
  });

  it('opens a note into the editor and Esc returns to the notes pane', async () => {
    const user = userEvent.setup();
    const { router } = renderTui('/notebooks/nb-1/notes');

    const notes = await screen.findByRole('listbox', { name: 'Notes' });
    await screen.findByText('Plans');
    await waitFor(() => expect(notes).toHaveFocus());

    await user.keyboard('{ArrowDown}{Enter}');
    expect(router.state.location.pathname).toBe('/notebooks/nb-1/notes/n-2');
    await waitFor(() => expect(screen.getByTestId('editor')).toHaveFocus());

    // Typing keys stay in the editor.
    await user.keyboard('{ArrowUp}');
    expect(router.state.location.pathname).toBe('/notebooks/nb-1/notes/n-2');

    await user.keyboard('{Escape}');
    await waitFor(() => expect(notes).toHaveFocus());
  });

  it('switches panes with Tab', async () => {
    const user = userEvent.setup();
    renderTui('/notebooks/nb-1/notes');

    const notes = await screen.findByRole('listbox', { name: 'Notes' });
    await waitFor(() => expect(notes).toHaveFocus());
    await user.keyboard('{Shift>}{Tab}{/Shift}');
    await waitFor(() => expect(screen.getByRole('listbox', { name: 'Notebooks' })).toHaveFocus());
  });

  // --- Function keys ---

  it('F7 creates a notebook from the notebooks pane', async () => {
    const user = userEvent.setup();
    vi.mocked(createNotebook).mockResolvedValue(notebook('nb-9', 'Recipes'));
    const { router } = renderTui('/notebooks');

    await waitFor(() => expect(screen.getByRole('listbox', { name: 'Notebooks' })).toHaveFocus());
    await user.keyboard('{F7}');
    const dialog = screen.getByRole('dialog', { name: 'New notebook' });
    await user.type(within(dialog).getByRole('textbox'), 'Recipes{Enter}');

    expect(createNotebook).toHaveBeenCalledWith('Recipes');
    await waitFor(() => expect(router.state.location.pathname).toBe('/notebooks/nb-9/notes'));
  });

  it('Alt+7 and Esc then 7 work like F7', async () => {
    const user = userEvent.setup();
    vi.mocked(createNote).mockResolvedValue(note('n-9', 'Todo'));
    renderTui('/notebooks/nb-1/notes');
    await waitFor(() => expect(screen.getByRole('listbox', { name: 'Notes' })).toHaveFocus());

    await user.keyboard('{Alt>}7{/Alt}');
    expect(screen.getByRole('dialog', { name: 'New note' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByRole('dialog', { name: 'New note' })).not.toBeInTheDocument();

    await user.keyboard('{Escape}7');
    expect(screen.getByRole('dialog', { name: 'New note' })).toBeInTheDocument();
  });

  it('F8 asks before deleting the note under the cursor', async () => {
    const user = userEvent.setup();
    vi.mocked(deleteNote).mockResolvedValue();
    renderTui('/notebooks/nb-1/notes');
    await screen.findByText('Groceries');
    await waitFor(() => expect(screen.getByRole('listbox', { name: 'Notes' })).toHaveFocus());

    await user.keyboard('{F8}');
    const confirm = screen.getByRole('alertdialog');
    expect(confirm).toHaveTextContent('Delete note "Groceries"?');
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));
    expect(deleteNote).toHaveBeenCalledWith('nb-1', 'n-1');
  });

  it('F6 filters the list', async () => {
    const user = userEvent.setup();
    renderTui('/notebooks/nb-1/notes');
    await screen.findByText('Plans');
    await waitFor(() => expect(screen.getByRole('listbox', { name: 'Notes' })).toHaveFocus());

    await user.keyboard('{F6}');
    await user.type(screen.getByRole('textbox'), 'gro{Enter}');

    const notes = screen.getByRole('listbox', { name: 'Notes' });
    expect(within(notes).getByText('Groceries')).toBeInTheDocument();
    expect(within(notes).queryByText('Plans')).not.toBeInTheDocument();
  });

  it('F3 hides the notebooks pane', async () => {
    const user = userEvent.setup();
    renderTui('/notebooks/nb-1/notes');
    await screen.findByRole('listbox', { name: 'Notebooks' });

    await user.keyboard('{F3}');
    expect(screen.queryByRole('listbox', { name: 'Notebooks' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'F3 Show' })).toBeInTheDocument();
  });

  it('F1 shows the help and any key closes it', async () => {
    const user = userEvent.setup();
    renderTui('/notebooks');

    await user.keyboard('{F1}');
    expect(screen.getByRole('dialog', { name: 'Keys' })).toBeInTheDocument();
    await user.keyboard('x');
    expect(screen.queryByRole('dialog', { name: 'Keys' })).not.toBeInTheDocument();
  });

  it('F10 and the key bar switch back to the classic layout', async () => {
    const user = userEvent.setup();
    const { router } = renderTui('/notebooks');

    await user.keyboard('{F10}');
    expect(router.state.location.search).toBe('?layout=auto');
  });

  it('runs function keys clicked on the key bar', async () => {
    const user = userEvent.setup();
    renderTui('/notebooks');
    await screen.findByRole('listbox', { name: 'Notebooks' });

    await user.click(screen.getByRole('button', { name: 'F7 New' }));
    expect(screen.getByRole('dialog', { name: 'New notebook' })).toBeInTheDocument();
  });

  // --- Menu bar ---

  it('F9 opens the menu; arrows and Enter run an item', async () => {
    const user = userEvent.setup();
    renderTui('/notebooks/nb-1/notes');
    await waitFor(() => expect(screen.getByRole('listbox', { name: 'Notes' })).toHaveFocus());

    await user.keyboard('{F9}');
    expect(screen.getByRole('menu', { name: 'File' })).toBeInTheDocument();
    await user.keyboard('{ArrowRight}{ArrowRight}');
    const view = screen.getByRole('menu', { name: 'View' });
    expect(within(view).getByRole('menuitem', { name: /Hide notebooks/ })).toHaveClass('cursor');

    await user.keyboard('{Enter}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(screen.queryByRole('listbox', { name: 'Notebooks' })).not.toBeInTheDocument();
  });

  it('Esc closes the menu', async () => {
    const user = userEvent.setup();
    renderTui('/notebooks');

    await user.click(screen.getByRole('button', { name: 'Options' }));
    expect(screen.getByRole('menuitemradio', { name: /System/ })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });
});
