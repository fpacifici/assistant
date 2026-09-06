import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router';
import NoteEditor from './NoteEditor';
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

const mockFetchNote = vi.mocked(fetchNote);
const mockFetchNodes = vi.mocked(fetchNodes);

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
