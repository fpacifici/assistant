import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { StrictMode } from 'react';
import { Route, Routes } from 'react-router';
import NoteEditor from './NoteEditor';
import Layout from './Layout';
import { renderWithProviders } from '../test/renderWithProviders';
import { AUTOSAVE_DELAY_MS } from '../hooks/useAutoSave';
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

vi.mock('../api/tags', () => ({
  fetchTags: vi.fn().mockResolvedValue([]),
  addNoteTag: vi.fn(),
  removeNoteTag: vi.fn(),
}));

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
    tags: [],
    preview: '',
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

async function makeDirty() {
  await waitFor(() => expect(onChangeCallback).toBeDefined());
  act(() => onChangeCallback?.());
}

async function elapseAutosave() {
  await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS));
}

function saveState(): HTMLElement {
  return screen.getByTestId('save-state');
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('NoteEditor permission gating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onChangeCallback = undefined;
    mockFetchNodes.mockResolvedValue([]);
  });

  it('has no Save button and no save state without update permission', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note']));
    renderEditor();

    await screen.findByRole('button', { name: 'Debug' });
    expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument();
    await makeDirty();
    await elapseAutosave();
    expect(mockExecuteSave).not.toHaveBeenCalled();
  });

  it('hides the Share button without share_note permission', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'update']));
    renderEditor();

    await screen.findByRole('button', { name: 'Debug' });
    expect(screen.queryByRole('button', { name: /share/i })).not.toBeInTheDocument();
  });

  it('shows the Share button with share_note permission', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'share_note']));
    renderEditor();

    await waitFor(() => expect(screen.getByRole('button', { name: /share/i })).toBeInTheDocument());
  });
});

// --- Auto-save ---

describe('NoteEditor auto-save', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onChangeCallback = undefined;
    mockFetchNodes.mockResolvedValue([]);
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'update']));
    mockExecuteSave.mockResolvedValue(new Map());
  });

  it('saves accumulated edits once after the delay and shows the save state', async () => {
    renderEditor();
    await waitFor(() => expect(saveState()).toHaveTextContent('Saved'));

    await makeDirty();
    expect(saveState()).toHaveTextContent('Unsaved changes');
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS - 1000));
    act(() => onChangeCallback?.());
    expect(mockExecuteSave).not.toHaveBeenCalled();

    await act(() => vi.advanceTimersByTimeAsync(1000));

    expect(mockExecuteSave).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(saveState()).toHaveTextContent('Saved'));
  });

  it('shows a save error and retries on the next edit', async () => {
    mockExecuteSave.mockRejectedValueOnce(new Error('500 boom'));
    renderEditor();
    await makeDirty();
    await elapseAutosave();

    expect(await screen.findByRole('status')).toHaveTextContent('Error: 500 boom');
    expect(saveState()).toHaveTextContent('Not saved');

    await makeDirty();
    await elapseAutosave();
    expect(mockExecuteSave).toHaveBeenCalledTimes(2);
    await waitFor(() => expect(saveState()).toHaveTextContent('Saved'));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('stops auto-saving after a conflict', async () => {
    mockExecuteSave.mockRejectedValue(new Error('409 Conflict'));
    renderEditor();
    await makeDirty();
    await elapseAutosave();

    expect(await screen.findByRole('status')).toHaveTextContent(/^Conflict/);

    await makeDirty();
    await elapseAutosave();
    expect(mockExecuteSave).toHaveBeenCalledTimes(1);
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

describe('NoteEditor on mobile', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onChangeCallback = undefined;
    mockFetchNodes.mockResolvedValue([]);
  });

  it('shows the save state in the top bar and no bottom toolbar', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'update']));
    const { container } = renderMobileEditor();

    expect(await within(topBar()).findByText('Saved')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /save/i })).not.toBeInTheDocument();
    expect(container.querySelector('.editor-toolbar')).toBeNull();
  });

  it('shows a conflict in the status line', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'update']));
    mockExecuteSave.mockRejectedValue(new Error('409 Conflict'));
    renderMobileEditor();

    await makeDirty();
    await elapseAutosave();

    expect(await screen.findByRole('status')).toHaveTextContent(/^Conflict/);
    expect(within(topBar()).getByText('Not saved')).toBeInTheDocument();
  });

  it('offers Share and Debug in the menu with share_note permission', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'share_note']));
    renderMobileEditor();

    await user.click(await screen.findByRole('button', { name: 'Menu' }));
    expect(await screen.findByRole('menuitem', { name: 'Share' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Debug' })).toBeInTheDocument();

    await user.click(screen.getByRole('menuitem', { name: 'Share' }));
    expect(await screen.findByRole('heading', { name: 'Share note' })).toBeInTheDocument();
  });

  it('omits Share from the menu without share_note permission', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockFetchNote.mockResolvedValue(makeNote(['view_note']));
    renderMobileEditor();

    await user.click(await screen.findByRole('button', { name: 'Menu' }));
    expect(await screen.findByRole('menuitem', { name: 'Debug' })).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', { name: 'Share' })).not.toBeInTheDocument();
  });

  it('opens Debug full screen and closes it', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockFetchNote.mockResolvedValue(makeNote(['view_note']));
    renderMobileEditor();

    await user.click(await screen.findByRole('button', { name: 'Menu' }));
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

// --- Unsaved-changes guard ---

describe('NoteEditor unsaved-changes guard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onChangeCallback = undefined;
    mockFetchNodes.mockResolvedValue([]);
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'update']));
  });

  it('saves pending edits and leaves via the mobile back arrow', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockExecuteSave.mockResolvedValue(new Map());
    const { router } = renderMobileEditor();
    await within(topBar()).findByText('Saved');
    await makeDirty();

    await user.click(screen.getByRole('link', { name: 'Back' }));

    await waitFor(() => expect(router.state.location.pathname).toBe('/notebooks/nb-1/notes'));
    expect(mockExecuteSave).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('lets the mobile back arrow through when clean', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    const { router } = renderMobileEditor();
    await within(topBar()).findByText('Saved');

    await user.click(screen.getByRole('link', { name: 'Back' }));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/notebooks/nb-1/notes');
    expect(mockExecuteSave).not.toHaveBeenCalled();
  });

  it('asks to discard when saving before switching notes fails', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    mockExecuteSave.mockRejectedValue(new Error('500 boom'));
    const { router } = renderEditor();
    await makeDirty();

    act(() => {
      router.navigate('/notebooks/nb-1/notes/note-2');
    });

    expect(await screen.findByRole('alertdialog')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/notebooks/nb-1/notes/note-1');

    await user.click(screen.getByRole('button', { name: 'Discard' }));
    expect(router.state.location.pathname).toBe('/notebooks/nb-1/notes/note-2');
  });

  it('does not ask after the auto-save completed', async () => {
    mockExecuteSave.mockResolvedValue(new Map());
    const { router } = renderEditor();
    await makeDirty();
    await elapseAutosave();
    await waitFor(() => expect(saveState()).toHaveTextContent('Saved'));

    await act(() => router.navigate('/notebooks/nb-1/notes/note-2'));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/notebooks/nb-1/notes/note-2');
    expect(mockExecuteSave).toHaveBeenCalledTimes(1);
  });
});

describe('NoteEditor on desktop', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    onChangeCallback = undefined;
    mockFetchNodes.mockResolvedValue([]);
  });

  it('keeps the save state, Debug and Share in the bottom toolbar', async () => {
    mockFetchNote.mockResolvedValue(makeNote(['view_note', 'update', 'share_note']));
    const { container } = renderEditor();

    await waitFor(() => expect(screen.getByRole('button', { name: /share/i })).toBeInTheDocument());
    const toolbar = container.querySelector('.editor-toolbar') as HTMLElement;
    expect(within(toolbar).getByText('Saved')).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: 'Debug' })).toBeInTheDocument();
    expect(within(toolbar).getByRole('button', { name: 'Share' })).toBeInTheDocument();
  });
});
