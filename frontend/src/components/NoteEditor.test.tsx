import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode } from 'react';
import { Route, Routes } from 'react-router';
import NoteEditor from './NoteEditor';
import Layout from './Layout';
import { renderWithProviders } from '../test/renderWithProviders';
import type { BlockNoteEditor } from '@blocknote/core';
import type { Note } from '../types';

vi.mock('../api/notes', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/notes')>()),
  fetchNote: vi.fn(),
}));
vi.mock('../api/nodes', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/nodes')>()),
  fetchNodes: vi.fn(),
}));

let onChangeCallback: (() => void) | undefined;

vi.mock('../markdown/reconcile', () => ({
  executeSave: vi.fn(),
}));
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

vi.mock('@blocknote/react', () => ({
  useCreateBlockNote: () => {
    onChangeCallback = undefined;
    return {
      isEditable: false,
      document: [],
      replaceBlocks: vi.fn(),
      tryParseMarkdownToBlocks: vi.fn(() => []),
      onChange: vi.fn((cb: () => void) => {
        onChangeCallback = cb;
        return () => {};
      }),
    } as unknown as BlockNoteEditor;
  },
}));

vi.mock('@blocknote/mantine', () => ({
  BlockNoteView: () => <div data-testid="blocknote-view" />,
}));

import { fetchNote } from '../api/notes';
import { fetchNodes } from '../api/nodes';
import { executeSave } from '../markdown/reconcile';

const mockFetchNote = vi.mocked(fetchNote);
const mockFetchNodes = vi.mocked(fetchNodes);
const mockExecuteSave = vi.mocked(executeSave);

function makeNote(permissions: string[]): Note {
  return {
    id: 'note-1',
    notebook_id: 'nb-1',
    owner_id: 'user-1',
    title: 'Title',
    creation_timestamp: '',
    update_timestamp: '',
    permissions,
  };
}

function renderEditor() {
  return renderWithProviders(
    <Routes>
      <Route path="/notebooks/:notebookId/notes/:noteId" element={<NoteEditor />} />
    </Routes>,
    { initialEntries: ['/notebooks/nb-1/notes/note-1'] },
  );
}

describe('NoteEditor permission gating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onChangeCallback = undefined;
    mockFetchNodes.mockResolvedValue([]);
  });

  it('disables the Save button and makes the editor read-only without update permission', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note']));
    renderEditor();

    await waitFor(() => expect(screen.getByRole('button', { name: /save/i })).toBeDisabled());
  });

  it('enables the Save button once dirty when the caller has update permission', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'update']));
    renderEditor();

    await waitFor(() => expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();

    await waitFor(() => expect(onChangeCallback).toBeDefined());
    act(() => onChangeCallback?.());

    expect(screen.getByRole('button', { name: /save/i })).not.toBeDisabled();
  });

  it('hides the Share button without share_note permission', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'update']));
    renderEditor();

    await waitFor(() => expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: /share/i })).not.toBeInTheDocument();
  });

  it('shows the Share button with share_note permission', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'share_note']));
    renderEditor();

    await waitFor(() => expect(screen.getByRole('button', { name: /share/i })).toBeInTheDocument());
  });
});

// --- Mobile chrome ---

const LAYOUT_ROUTES = [
  {
    path: '/notebooks/:notebookId/notes/:noteId',
    element: (
      <StrictMode>
        <Layout />
      </StrictMode>
    ),
  },
];

function renderMobileEditor() {
  return renderWithProviders(null, {
    routes: LAYOUT_ROUTES,
    initialEntries: ['/notebooks/nb-1/notes/note-1'],
    layout: 'mobile',
  });
}

function topBar(): HTMLElement {
  return screen.getByRole('banner');
}

async function makeDirty() {
  await waitFor(() => expect(onChangeCallback).toBeDefined());
  act(() => onChangeCallback?.());
}

describe('NoteEditor on mobile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onChangeCallback = undefined;
    mockFetchNodes.mockResolvedValue([]);
  });

  it('renders Save in the top bar instead of the bottom toolbar', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'update']));
    const { container } = renderMobileEditor();

    const save = await within(topBar()).findByRole('button', { name: 'Save' });
    expect(save).toBeDisabled();
    expect(container.querySelector('.editor-toolbar')).toBeNull();
    expect(screen.getAllByRole('button', { name: 'Save' })).toHaveLength(1);
  });

  it('enables Save once dirty and saves from the top bar', async () => {
    const user = userEvent.setup();
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'update']));
    mockExecuteSave.mockResolvedValue(new Map());
    renderMobileEditor();

    await within(topBar()).findByRole('button', { name: 'Save' });
    await makeDirty();
    const save = within(topBar()).getByRole('button', { name: 'Save' });
    expect(save).not.toBeDisabled();

    await user.click(save);

    expect(mockExecuteSave).toHaveBeenCalled();
    expect(await screen.findByRole('status')).toHaveTextContent('Saved');
  });

  it('shows a conflict in the status line', async () => {
    const user = userEvent.setup();
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'update']));
    mockExecuteSave.mockRejectedValue(new Error('409 Conflict'));
    renderMobileEditor();

    await within(topBar()).findByRole('button', { name: 'Save' });
    await makeDirty();
    await user.click(within(topBar()).getByRole('button', { name: 'Save' }));

    expect(await screen.findByRole('status')).toHaveTextContent(/^Conflict/);
  });

  it('keeps Save disabled without update permission', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note']));
    renderMobileEditor();

    await within(topBar()).findByRole('button', { name: 'Save' });
    await makeDirty();
    expect(within(topBar()).getByRole('button', { name: 'Save' })).toBeDisabled();
  });

  it('offers Share and Debug in the menu with share_note permission', async () => {
    const user = userEvent.setup();
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'share_note']));
    renderMobileEditor();
    await within(topBar()).findByRole('button', { name: 'Save' });

    await user.click(screen.getByRole('button', { name: 'Menu' }));
    expect(await screen.findByRole('menuitem', { name: 'Share' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Debug' })).toBeInTheDocument();

    await user.click(screen.getByRole('menuitem', { name: 'Share' }));
    expect(await screen.findByRole('heading', { name: 'Share note' })).toBeInTheDocument();
  });

  it('omits Share from the menu without share_note permission', async () => {
    const user = userEvent.setup();
    mockFetchNote.mockResolvedValue(makeNote(['view_note']));
    renderMobileEditor();
    await within(topBar()).findByRole('button', { name: 'Save' });

    await user.click(screen.getByRole('button', { name: 'Menu' }));
    expect(await screen.findByRole('menuitem', { name: 'Debug' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Share' })).not.toBeInTheDocument();
  });

  it('opens Debug full screen and closes it', async () => {
    const user = userEvent.setup();
    mockFetchNote.mockResolvedValue(makeNote(['view_note']));
    renderMobileEditor();
    await within(topBar()).findByRole('button', { name: 'Save' });

    await user.click(screen.getByRole('button', { name: 'Menu' }));
    await user.click(await screen.findByRole('menuitem', { name: 'Debug' }));

    const panel = screen.getByRole('dialog', { name: 'Debug blocks' });
    expect(panel).toHaveClass('fullscreen-panel');
    expect(within(panel).getByText(/Block structure/)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Menu' }));
    expect(screen.getByRole('menuitem', { name: 'Hide Debug' })).toBeInTheDocument();
    await user.keyboard('{Escape}');

    await user.click(within(panel).getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('dialog', { name: 'Debug blocks' })).not.toBeInTheDocument();
  });

  it('renders the formatting toolbar', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'update']));
    renderMobileEditor();
    expect(await screen.findByTitle('Bold')).toBeInTheDocument();
  });
});

describe('NoteEditor on desktop', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onChangeCallback = undefined;
    mockFetchNodes.mockResolvedValue([]);
  });

  it('keeps Save, Debug and Share in the bottom toolbar', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'share_note']));
    const { container } = renderEditor();

    await waitFor(() => expect(screen.getByRole('button', { name: /share/i })).toBeInTheDocument());
    const toolbar = container.querySelector('.editor-toolbar') as HTMLElement;
    expect(within(toolbar).getByRole('button', { name: 'Save' })).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: 'Debug' })).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: 'Share' })).toBeInTheDocument();
  });
});
