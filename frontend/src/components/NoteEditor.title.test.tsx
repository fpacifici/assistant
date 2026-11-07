import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Route, Routes } from 'react-router';
import { QueryClient } from '@tanstack/react-query';
import type { InfiniteData } from '@tanstack/react-query';
import NoteEditor from './NoteEditor';
import { renderWithProviders } from '../test/renderWithProviders';
import { AUTOSAVE_DELAY_MS } from '../hooks/useAutoSave';
import type { BlockNoteEditor } from '@blocknote/core';
import type { Note } from '../types';

vi.mock('../api/notes', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/notes')>()),
  fetchNote: vi.fn(),
  updateNoteTitle: vi.fn(),
}));
vi.mock('../api/nodes', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/nodes')>()),
  fetchNodes: vi.fn(),
}));
vi.mock('../api/tags', () => ({
  fetchTags: vi.fn().mockResolvedValue([]),
  addNoteTag: vi.fn(),
  removeNoteTag: vi.fn(),
}));
vi.mock('../markdown/reconcile', () => ({ executeSave: vi.fn() }));
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

const FIRST_BLOCK = { id: 'b1', type: 'paragraph' };
const editorMock = {
  focus: vi.fn(),
  setTextCursorPosition: vi.fn(),
};

vi.mock('@blocknote/react', () => ({
  useCreateBlockNote: () =>
    ({
      isEditable: false,
      document: [FIRST_BLOCK],
      replaceBlocks: vi.fn(),
      tryParseMarkdownToBlocks: vi.fn(() => []),
      onChange: vi.fn(() => () => {}),
      focus: editorMock.focus,
      setTextCursorPosition: editorMock.setTextCursorPosition,
    }) as unknown as BlockNoteEditor,
}));
vi.mock('@blocknote/mantine', () => ({
  BlockNoteView: () => <div data-testid="blocknote-view" />,
}));

import { fetchNote, updateNoteTitle } from '../api/notes';
import { fetchNodes } from '../api/nodes';

function note(fields: Partial<Note> = {}): Note {
  return {
    id: 'note-1',
    notebook_id: 'nb-1',
    owner_id: 'user-1',
    title: 'Groceries',
    creation_timestamp: '',
    update_timestamp: '',
    permissions: ['view_note', 'update'],
    tags: [],
    preview: '',
    ...fields,
  };
}

function renderEditor(
  path = '/notebooks/nb-1/notes/note-1',
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } }),
) {
  return renderWithProviders(
    <Routes>
      <Route path="/notebooks/:notebookId/notes/:noteId" element={<NoteEditor />} />
      <Route path="/notebooks/:notebookId/notes" element={<div>Note list</div>} />
    </Routes>,
    { initialEntries: [path], queryClient },
  );
}

/** A client whose note list holds this note and another one. */
function seededList(): QueryClient {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData<InfiniteData<Note[]>>(['notes', 'nb-1'], {
    pages: [[note(), note({ id: 'note-2', title: 'Other' })]],
    pageParams: [0],
  });
  return queryClient;
}

function listTitles(queryClient: QueryClient): string[] | undefined {
  return queryClient
    .getQueryData<InfiniteData<Note[]>>(['notes', 'nb-1'])
    ?.pages.flat()
    .map((item) => item.title);
}

function titleField(): Promise<HTMLTextAreaElement> {
  return screen.findByRole('textbox', { name: 'Note title' }) as Promise<HTMLTextAreaElement>;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.mocked(fetchNodes).mockResolvedValue([]);
  vi.mocked(fetchNote).mockResolvedValue(note());
  vi.mocked(updateNoteTitle).mockImplementation(async (_nb, _id, title) => note({ title }));
});

afterEach(() => {
  vi.useRealTimers();
});

// --- Showing the title ---

describe('note title', () => {
  it('shows the title at the top of the note as an H2, before the text', async () => {
    renderEditor();

    const field = await titleField();
    expect(field).toHaveValue('Groceries');
    const heading = screen.getByRole('heading', { level: 2 });
    expect(heading).toContainElement(field);
    expect(
      heading.compareDocumentPosition(screen.getByTestId('blocknote-view')) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('shows a placeholder for an untitled note', async () => {
    vi.mocked(fetchNote).mockResolvedValue(note({ title: '' }));
    renderEditor();

    expect(await titleField()).toHaveAttribute('placeholder', 'Untitled');
  });

  it('is read-only without update permission', async () => {
    vi.mocked(fetchNote).mockResolvedValue(note({ permissions: ['view_note'] }));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderEditor();

    const field = await titleField();
    expect(field).toHaveAttribute('readonly');
    await user.type(field, 'x');
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS));

    expect(field).toHaveValue('Groceries');
    expect(updateNoteTitle).not.toHaveBeenCalled();
  });
});

// --- Editing the title ---

describe('editing the title', () => {
  it('saves the new title after the autosave delay', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderEditor();

    const field = await titleField();
    await user.clear(field);
    await user.type(field, 'Shopping list');
    expect(screen.getByTestId('save-state')).toHaveTextContent('Unsaved changes');

    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS));

    expect(updateNoteTitle).toHaveBeenCalledTimes(1);
    expect(updateNoteTitle).toHaveBeenCalledWith('nb-1', 'note-1', 'Shopping list');
    await waitFor(() => expect(screen.getByTestId('save-state')).toHaveTextContent('Saved'));
    expect(field).toHaveValue('Shopping list');
  });

  it('updates the title in the note list while typing, before any save', async () => {
    const queryClient = seededList();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderEditor(undefined, queryClient);

    const field = await titleField();
    await user.clear(field);
    await user.type(field, 'Renamed');

    expect(listTitles(queryClient)).toEqual(['Renamed', 'Other']);
    expect(updateNoteTitle).not.toHaveBeenCalled();
  });

  it('puts the saved title back in the note list on Escape', async () => {
    const queryClient = seededList();
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderEditor(undefined, queryClient);

    await user.type(await titleField(), ' oops');
    expect(listTitles(queryClient)).toEqual(['Groceries oops', 'Other']);
    await user.keyboard('{Escape}');

    expect(listTitles(queryClient)).toEqual(['Groceries', 'Other']);
  });

  it('saves when leaving the field, trimmed', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderEditor();

    const field = await titleField();
    await user.clear(field);
    await user.type(field, '  Trip  ');
    await user.tab();

    await waitFor(() => expect(updateNoteTitle).toHaveBeenCalledWith('nb-1', 'note-1', 'Trip'));
    await waitFor(() => expect(field).toHaveValue('Trip'));
  });

  it('Enter saves and moves to the start of the text, with no new line', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderEditor();

    const field = await titleField();
    await user.type(field, ' today{Enter}');

    expect(field).toHaveValue('Groceries today');
    await waitFor(() =>
      expect(updateNoteTitle).toHaveBeenCalledWith('nb-1', 'note-1', 'Groceries today'),
    );
    expect(editorMock.setTextCursorPosition).toHaveBeenCalledWith(FIRST_BLOCK, 'start');
    expect(editorMock.focus).toHaveBeenCalled();
  });

  it('turns pasted line breaks into spaces', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderEditor();

    const field = await titleField();
    await user.clear(field);
    await user.click(field);
    await user.paste('Two\nlines');

    expect(field).toHaveValue('Two lines');
  });

  it('Escape drops the unsaved title', async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderEditor();

    const field = await titleField();
    await user.type(field, ' oops');
    await user.keyboard('{Escape}');
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS));

    expect(field).toHaveValue('Groceries');
    expect(updateNoteTitle).not.toHaveBeenCalled();
    expect(screen.getByTestId('save-state')).toHaveTextContent('Saved');
  });

  it('shows an error when the title cannot be saved', async () => {
    vi.mocked(updateNoteTitle).mockRejectedValue(new Error('boom'));
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderEditor();

    await user.type(await titleField(), '!');
    await act(() => vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS));

    expect(await screen.findByText('Error saving the title: boom')).toBeInTheDocument();
    expect(screen.getByTestId('save-state')).toHaveTextContent('Not saved');
  });

  it('saves a pending title before opening the note in a new window', async () => {
    const popup = { close: vi.fn(), focus: vi.fn(), location: { href: '' } };
    const open = vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window);
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderEditor();

    await user.type(await titleField(), '!');
    await user.click(screen.getByRole('button', { name: 'Open in new window' }));

    await waitFor(() => expect(popup.location.href).not.toBe(''));
    expect(updateNoteTitle).toHaveBeenCalledWith('nb-1', 'note-1', 'Groceries!');
    open.mockRestore();
  });
});
