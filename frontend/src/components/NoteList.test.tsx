import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import NoteList, { formatNoteDate } from './NoteList';
import { renderWithProviders } from '../test/renderWithProviders';
import { Route, Routes } from 'react-router';

vi.mock('../api/notes', () => ({
  fetchNotes: vi.fn(),
  createNote: vi.fn(),
  deleteNote: vi.fn(),
}));

vi.mock('../api/notebooks', () => ({
  fetchNotebook: vi.fn().mockResolvedValue({
    id: 'nb-1', name: 'algorithms', owner_id: 'test-user', permissions: [],
  }),
}));

import { fetchNotes, createNote, deleteNote } from '../api/notes';
import { PAGE_SIZE } from '../api/pagination';
import type { Note } from '../types';
import { mockIntersectionObserver, scrollIntoView } from '../test/intersectionObserver';

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

function makeNote(i: number, overrides: Partial<Note> = {}): Note {
  return {
    id: `note-${i}`, notebook_id: 'nb-1', owner_id: 'test-user', title: `Note ${i}`,
    creation_timestamp: '', update_timestamp: '', permissions: ['view_note'], tags: [],
    preview: '', ...overrides,
  };
}

describe('NoteList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIntersectionObserver();
  });

  it('titles the list with the notebook name', async () => {
    mockFetchNotes.mockResolvedValue([]);
    renderNoteList();
    expect(await screen.findByRole('heading', { name: 'algorithms' })).toBeInTheDocument();
  });

  it('shows the date and preview of each note', async () => {
    mockFetchNotes.mockResolvedValue([
      makeNote(1, {
        title: 'Hilbert curves',
        update_timestamp: '2026-05-11T10:00:00Z',
        preview: 'A way to sort multidimensional data',
      }),
    ]);
    renderNoteList();

    const row = (await screen.findByText('Hilbert curves')).closest('li')!;
    expect(within(row).getByText('A way to sort multidimensional data')).toBeInTheDocument();
    expect(within(row).getByText(formatNoteDate('2026-05-11T10:00:00Z'))).toBeInTheDocument();
  });

  it('requests the first page of PAGE_SIZE notes', async () => {
    mockFetchNotes.mockResolvedValue([makeNote(1)]);
    renderNoteList();
    await screen.findByText('Note 1');
    expect(mockFetchNotes).toHaveBeenCalledTimes(1);
    expect(mockFetchNotes).toHaveBeenCalledWith('nb-1', 0);
  });

  it('loads the next page when the end of the list scrolls into view', async () => {
    const firstPage = Array.from({ length: PAGE_SIZE }, (_, i) => makeNote(i));
    mockFetchNotes
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce([makeNote(PAGE_SIZE, { title: 'Last note' })]);
    const { container } = renderNoteList();
    await screen.findByText('Note 0');

    scrollIntoView(container.querySelector('.list-sentinel')!);

    expect(await screen.findByText('Last note')).toBeInTheDocument();
    expect(mockFetchNotes).toHaveBeenLastCalledWith('nb-1', PAGE_SIZE);
    // A short page ends the list.
    expect(container.querySelector('.list-sentinel')).not.toBeInTheDocument();
  });

  it('has no sentinel when the first page is short', async () => {
    mockFetchNotes.mockResolvedValue([makeNote(1)]);
    const { container } = renderNoteList();
    await screen.findByText('Note 1');
    expect(container.querySelector('.list-sentinel')).not.toBeInTheDocument();
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
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'test-user', title: 'First Note', creation_timestamp: '', update_timestamp: '', permissions: ['view_note'], tags: [], preview: '' },
      { id: 'note-2', notebook_id: 'nb-1', owner_id: 'test-user', title: 'Second Note', creation_timestamp: '', update_timestamp: '', permissions: ['view_note'], tags: [], preview: '' },
    ]);
    renderNoteList();

    await waitFor(() => {
      expect(screen.getByText('First Note')).toBeInTheDocument();
    });
    expect(screen.getByText('Second Note')).toBeInTheDocument();
  });

  it('renders tag chips under each note with a +N overflow', async () => {
    const tags = ['a', 'b', 'c', 'd', 'e'].map((name) => ({ id: `t-${name}`, name }));
    mockFetchNotes.mockResolvedValue([
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'test-user', title: 'Tagged', creation_timestamp: '', update_timestamp: '', permissions: ['view_note'], tags, preview: '' },
    ]);
    renderNoteList();

    await waitFor(() => expect(screen.getByText('Tagged')).toBeInTheDocument());
    const row = screen.getByText('Tagged').closest('li')!;
    expect(within(row).getByText('a')).toBeInTheDocument();
    expect(within(row).getByText('c')).toBeInTheDocument();
    expect(within(row).queryByText('d')).not.toBeInTheDocument();
    expect(within(row).getByText('+2')).toHaveAttribute('title', 'd, e');
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
      permissions: ['view_note'], tags: [], preview: '',
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
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'test-user', title: 'Delete Me', creation_timestamp: '', update_timestamp: '', permissions: ['delete_note'], tags: [], preview: '' },
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
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'test-user', title: 'Keep Me', creation_timestamp: '', update_timestamp: '', permissions: ['delete_note'], tags: [], preview: '' },
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
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'test-user', title: 'Phone Note', creation_timestamp: '', update_timestamp: '', permissions: ['delete_note'], tags: [], preview: '' },
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
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'other-user', title: 'Read Only', creation_timestamp: '', update_timestamp: '', permissions: ['view_note'], tags: [], preview: '' },
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
      { id: 'note-1', notebook_id: 'nb-1', owner_id: 'other-user', title: 'Shared', creation_timestamp: '', update_timestamp: '', permissions: ['view_note', 'share_note'], tags: [], preview: '' },
    ]);
    renderNoteList();

    await waitFor(() => {
      expect(screen.getByTitle('Share note')).toBeInTheDocument();
    });
    expect(screen.queryByTitle('Delete note')).not.toBeInTheDocument();
  });
});

describe('formatNoteDate', () => {
  const now = new Date('2026-10-09T12:00:00Z');

  it('omits the year for dates in the current year', () => {
    expect(formatNoteDate('2026-05-11T12:00:00Z', now)).not.toMatch(/2026/);
  });

  it('includes the year for older dates', () => {
    expect(formatNoteDate('2025-05-11T12:00:00Z', now)).toMatch(/2025/);
  });

  it('returns an empty string for missing or invalid timestamps', () => {
    expect(formatNoteDate('', now)).toBe('');
    expect(formatNoteDate('not a date', now)).toBe('');
  });
});
