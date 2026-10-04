import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import Layout from './Layout';
import { renderWithProviders } from '../test/renderWithProviders';
import { mockViewport, resizeViewport } from '../test/matchMedia';
import type { LayoutMode } from '../layout/layoutMode';

const mockLogout = vi.fn();

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      uid: 'u1',
      email: 'a@b.com',
      firstname: 'Test',
      lastname: 'User',
      invite_quota_remaining: 3,
    },
    logout: mockLogout,
  }),
}));

let mockInvitesEnabled = true;

vi.mock('../api/invites', () => ({
  fetchInvitesConfig: vi.fn(() =>
    Promise.resolve({ registration_enabled: true, invites_enabled: mockInvitesEnabled }),
  ),
}));

vi.mock('../api/notebooks', () => ({
  fetchNotebooks: vi.fn().mockResolvedValue([
    { id: 'nb-1', name: 'Work notebook', owner_id: 'u1', permissions: [] },
  ]),
}));

vi.mock('../api/notes', () => ({
  fetchNote: vi.fn().mockResolvedValue({
    id: 'note-1',
    notebook_id: 'nb-1',
    owner_id: 'u1',
    title: 'Meeting notes',
    creation_timestamp: '',
    update_timestamp: '',
    permissions: [],
    tags: [],
  }),
}));
vi.mock('../api/tags', () => ({
  fetchTags: vi.fn().mockResolvedValue([]),
  addNoteTag: vi.fn(),
  removeNoteTag: vi.fn(),
}));

vi.mock('./NotebookList', () => ({
  default: () => <div data-testid="notebook-list">NotebookList</div>,
}));

vi.mock('./NoteList', () => ({
  default: () => <div data-testid="note-list">NoteList</div>,
}));

// Stateful stand-in: its local state survives only if the instance is reused.
vi.mock('./NoteEditor', () => ({
  default: function FakeNoteEditor() {
    const [text, setText] = useState('');
    return (
      <div data-testid="note-editor">
        <input aria-label="draft" value={text} onChange={(e) => setText(e.target.value)} />
      </div>
    );
  },
}));

const ROUTES = [
  { path: '/notebooks', element: <Layout /> },
  { path: '/notebooks/:notebookId/notes', element: <Layout /> },
  { path: '/notebooks/:notebookId/notes/:noteId', element: <Layout /> },
];

function renderLayout(path: string, layout: LayoutMode | 'auto' = 'desktop') {
  return renderWithProviders(null, { routes: ROUTES, initialEntries: [path], layout });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockInvitesEnabled = true;
});

// --- Shared across modes ---

describe.each(['desktop', 'mobile'] as const)('Layout (%s)', (layout) => {
  it('renders NotebookList at /notebooks', () => {
    renderLayout('/notebooks', layout);
    expect(screen.getByTestId('notebook-list')).toBeInTheDocument();
    expect(screen.queryByTestId('note-list')).not.toBeInTheDocument();
    expect(screen.queryByTestId('note-editor')).not.toBeInTheDocument();
  });

  it('renders NoteList when a notebook is selected', () => {
    renderLayout('/notebooks/nb-1/notes', layout);
    expect(screen.getByTestId('note-list')).toBeInTheDocument();
    expect(screen.queryByTestId('note-editor')).not.toBeInTheDocument();
  });

  it('renders NoteEditor when a note is selected', () => {
    renderLayout('/notebooks/nb-1/notes/note-1', layout);
    expect(screen.getByTestId('note-editor')).toBeInTheDocument();
  });

  it('marks the shell with the layout mode', () => {
    const { container } = renderLayout('/notebooks', layout);
    expect(container.querySelector('.app-shell')).toHaveAttribute('data-layout', layout);
  });
});

// --- Desktop ---

describe('Layout (desktop)', () => {
  it('shows the invites nav link and quota badge when invites are enabled', async () => {
    renderLayout('/notebooks');
    expect(await screen.findByRole('link', { name: 'Invites' })).toHaveAttribute(
      'href',
      '/invites',
    );
    expect(screen.getByText('3 invites left')).toBeInTheDocument();
    expect(screen.getByText('Test User')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Logout' })).toBeInTheDocument();
  });

  it('shows placeholder when no notebook is selected', () => {
    renderLayout('/notebooks');
    expect(screen.getByText('Select a notebook to get started')).toBeInTheDocument();
  });

  it('shows NotebookList and NoteList next to the placeholder when a notebook is selected', () => {
    renderLayout('/notebooks/nb-1/notes');
    expect(screen.getByTestId('notebook-list')).toBeInTheDocument();
    expect(screen.getByText('Select a note to edit')).toBeInTheDocument();
  });

  it('shows the lists next to the editor when a note is selected', () => {
    renderLayout('/notebooks/nb-1/notes/note-1');
    expect(screen.getByTestId('notebook-list')).toBeInTheDocument();
    expect(screen.getByTestId('note-list')).toBeInTheDocument();
  });

  it('has no mobile top bar', () => {
    renderLayout('/notebooks/nb-1/notes');
    expect(screen.queryByRole('link', { name: 'Back' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Menu' })).not.toBeInTheDocument();
  });
});

// --- Mobile ---

describe('Layout (mobile)', () => {
  it('shows only the notebook list at /notebooks, titled "Notebooks", without back', () => {
    renderLayout('/notebooks', 'mobile');
    expect(screen.getByRole('heading', { name: 'Notebooks' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Back' })).not.toBeInTheDocument();
    expect(screen.queryByText('Select a notebook to get started')).not.toBeInTheDocument();
  });

  it('shows only the note list for a notebook, titled with its name', async () => {
    renderLayout('/notebooks/nb-1/notes', 'mobile');
    expect(screen.queryByTestId('notebook-list')).not.toBeInTheDocument();
    expect(screen.queryByText('Select a note to edit')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back' })).toHaveAttribute('href', '/notebooks');
    expect(await screen.findByRole('heading', { name: 'Work notebook' })).toBeInTheDocument();
  });

  it('shows only the editor for a note, titled with the note title', async () => {
    renderLayout('/notebooks/nb-1/notes/note-1', 'mobile');
    expect(screen.queryByTestId('notebook-list')).not.toBeInTheDocument();
    expect(screen.queryByTestId('note-list')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back' })).toHaveAttribute(
      'href',
      '/notebooks/nb-1/notes',
    );
    expect(await screen.findByRole('heading', { name: 'Meeting notes' })).toBeInTheDocument();
  });

  it('hides account details until the menu is opened', async () => {
    const user = userEvent.setup();
    renderLayout('/notebooks', 'mobile');
    expect(screen.queryByText('Test User')).not.toBeInTheDocument();
    expect(screen.queryByText('3 invites left')).not.toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Logout' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Menu' }));

    const menu = screen.getByRole('menu');
    expect(within(menu).getByText('Test User')).toBeInTheDocument();
    expect(within(menu).getByText('3 invites left')).toBeInTheDocument();
    expect(await within(menu).findByRole('menuitem', { name: 'Invites' })).toHaveAttribute(
      'href',
      '/invites',
    );
  });

  it('omits the Invites entry when invites are disabled', async () => {
    mockInvitesEnabled = false;
    const user = userEvent.setup();
    renderLayout('/notebooks', 'mobile');
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    await screen.findByRole('menuitem', { name: 'Logout' });
    expect(screen.queryByRole('menuitem', { name: 'Invites' })).not.toBeInTheDocument();
  });

  it('logs out from the menu', async () => {
    const user = userEvent.setup();
    renderLayout('/notebooks', 'mobile');
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    await user.click(screen.getByRole('menuitem', { name: 'Logout' }));
    expect(mockLogout).toHaveBeenCalled();
  });
});

// --- Mode switch ---

describe('Layout mode switch', () => {
  const originalMatchMedia = window.matchMedia;

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    sessionStorage.clear();
  });

  it('keeps the same editor instance when the viewport crosses the breakpoint', async () => {
    mockViewport(1440, 900);
    const user = userEvent.setup();
    renderLayout('/notebooks/nb-1/notes/note-1', 'auto');

    await user.type(screen.getByLabelText('draft'), 'unsaved');
    expect(screen.getByTestId('note-list')).toBeInTheDocument();

    act(() => resizeViewport(390, 844));
    expect(screen.queryByTestId('note-list')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Menu' })).toBeInTheDocument();
    expect(screen.getByLabelText('draft')).toHaveValue('unsaved');

    act(() => resizeViewport(1440, 900));
    expect(screen.getByTestId('note-list')).toBeInTheDocument();
    expect(screen.getByLabelText('draft')).toHaveValue('unsaved');
  });

  it('keeps the same editor instance when the override flips the mode', async () => {
    mockViewport(1440, 900);
    const user = userEvent.setup();
    const { router } = renderLayout('/notebooks/nb-1/notes/note-1', 'auto');

    await user.type(screen.getByLabelText('draft'), 'unsaved');
    await act(() => router.navigate('/notebooks/nb-1/notes/note-1?layout=mobile'));
    expect(screen.getByRole('button', { name: 'Menu' })).toBeInTheDocument();
    expect(screen.getByLabelText('draft')).toHaveValue('unsaved');
  });
});
