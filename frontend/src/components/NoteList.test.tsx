import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import NoteList from './NoteList';
import { renderWithProviders } from '../test/renderWithProviders';
import { Route, Routes } from 'react-router';

vi.mock('../api/notes', () => ({
  fetchNotes: vi.fn(),
  createNote: vi.fn(),
  deleteNote: vi.fn(),
}));

import { fetchNotes, createNote, deleteNote } from '../api/notes';

const mockFetchNotes = vi.mocked(fetchNotes);
const mockCreateNote = vi.mocked(createNote);
const mockDeleteNote = vi.mocked(deleteNote);

function renderNoteList(path = '/notebooks/nb-1/notes') {
  return renderWithProviders(
    <Routes>
      <Route path="/notebooks/:notebookId/notes" element={<NoteList />} />
      <Route path="/notebooks/:notebookId/notes/:noteId" element={<NoteList />} />
    </Routes>,
    { initialEntries: [path] },
  );
}

describe('NoteList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing without notebookId', () => {
    renderWithProviders(
      <Routes>
        <Route path="/" element={<NoteList />} />
      </Routes>,
      { initialEntries: ['/'] },
    );
    expect(screen.queryByText('Notes')).not.toBeInTheDocument();
  });

  it('shows loading state', () => {
    mockFetchNotes.mockReturnValue(new Promise(() => {}));
    renderNoteList();
    expect(screen.getByText('Loading notes...')).toBeInTheDocument();
  });

  it('renders notes list', async () => {
    mockFetchNotes.mockResolvedValue([
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'test-user', title: 'First Note', creation_timestamp: '', update_timestamp: '', permissions: ['view_note'] },
      { id: 'note-2', notebook_id: 'nb-1', owner_id: 'test-user', title: 'Second Note', creation_timestamp: '', update_timestamp: '', permissions: ['view_note'] },
    ]);
    renderNoteList();

    await waitFor(() => {
      expect(screen.getByText('First Note')).toBeInTheDocument();
    });
    expect(screen.getByText('Second Note')).toBeInTheDocument();
  });

  it('shows empty state', async () => {
    mockFetchNotes.mockResolvedValue([]);
    renderNoteList();

    await waitFor(() => {
      expect(screen.getByText('No notes yet')).toBeInTheDocument();
    });
  });

  it('creates a note on form submit', async () => {
    const user = userEvent.setup();
    mockFetchNotes.mockResolvedValue([]);
    mockCreateNote.mockResolvedValue({
      id: 'note-new', notebook_id: 'nb-1', owner_id: 'test-user',
      title: 'My Note', creation_timestamp: '', update_timestamp: '',
      permissions: ['view_note'],
    });

    renderNoteList();
    await waitFor(() => {
      expect(screen.getByPlaceholderText('New note title')).toBeInTheDocument();
    });

    await user.type(screen.getByPlaceholderText('New note title'), 'My Note');
    await user.click(screen.getByText('Create'));

    await waitFor(() => {
      expect(mockCreateNote).toHaveBeenCalledWith('nb-1', 'My Note');
    });
  });

  it('asks for confirmation and deletes on confirm', async () => {
    const user = userEvent.setup();
    mockFetchNotes.mockResolvedValue([
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'test-user', title: 'Delete Me', creation_timestamp: '', update_timestamp: '', permissions: ['delete_note'] },
    ]);
    mockDeleteNote.mockResolvedValue(undefined);

    renderNoteList();
    await waitFor(() => {
      expect(screen.getByText('Delete Me')).toBeInTheDocument();
    });

    await user.click(screen.getByTitle('Delete note'));

    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('Delete note "Delete Me"? This cannot be undone.');
    expect(mockDeleteNote).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(mockDeleteNote).toHaveBeenCalledWith('nb-1', 'note-1');
    });
  });

  it('does not delete when the confirmation is cancelled', async () => {
    const user = userEvent.setup();
    mockFetchNotes.mockResolvedValue([
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'test-user', title: 'Keep Me', creation_timestamp: '', update_timestamp: '', permissions: ['delete_note'] },
    ]);

    renderNoteList();
    await screen.findByText('Keep Me');

    await user.click(screen.getByTitle('Delete note'));
    await user.keyboard('{Escape}');

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(mockDeleteNote).not.toHaveBeenCalled();
  });

  it('confirms deletion in mobile mode too', async () => {
    const user = userEvent.setup();
    mockFetchNotes.mockResolvedValue([
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'test-user', title: 'Phone Note', creation_timestamp: '', update_timestamp: '', permissions: ['delete_note'] },
    ]);

    renderWithProviders(
      <Routes>
        <Route path="/notebooks/:notebookId/notes" element={<NoteList />} />
      </Routes>,
      { initialEntries: ['/notebooks/nb-1/notes'], layout: 'mobile' },
    );
    await screen.findByText('Phone Note');

    await user.click(screen.getByTitle('Delete note'));
    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(mockDeleteNote).not.toHaveBeenCalled();
  });
});

describe('NoteList permission gating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('hides share and delete buttons when permissions lack them', async () => {
    mockFetchNotes.mockResolvedValue([
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'other-user', title: 'Read Only', creation_timestamp: '', update_timestamp: '', permissions: ['view_note'] },
    ]);
    renderNoteList();

    await waitFor(() => {
      expect(screen.getByText('Read Only')).toBeInTheDocument();
    });
    expect(screen.queryByTitle('Share note')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Delete note')).not.toBeInTheDocument();
  });

  it('shows share button when share_note permission is present', async () => {
    mockFetchNotes.mockResolvedValue([
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'other-user', title: 'Shared', creation_timestamp: '', update_timestamp: '', permissions: ['view_note', 'share_note'] },
    ]);
    renderNoteList();

    await waitFor(() => {
      expect(screen.getByTitle('Share note')).toBeInTheDocument();
    });
    expect(screen.queryByTitle('Delete note')).not.toBeInTheDocument();
  });
});
