import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PromoteDialog from './PromoteDialog';
import { ApiError } from '../../api/client';
import { readingLink } from '../../test/readingLinks';
import { renderWithProviders } from '../../test/renderWithProviders';
import type { Note, SearchResponse } from '../../types';

vi.mock('../../api/reading', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/reading')>()),
  fetchSuggestions: vi.fn(),
  promoteLink: vi.fn(),
}));
vi.mock('../../api/search', () => ({ searchNotes: vi.fn() }));
vi.mock('../../api/notebooks', () => ({ fetchNotebooks: vi.fn() }));

import { fetchNotebooks } from '../../api/notebooks';
import { fetchSuggestions, promoteLink } from '../../api/reading';
import { searchNotes } from '../../api/search';

const onClose = vi.fn();

function note(id: string, title: string, permissions: string[]): Note {
  return {
    id,
    notebook_id: 'nb1',
    owner_id: 'u1',
    title,
    creation_timestamp: '2026-10-01T00:00:00Z',
    update_timestamp: '2026-10-01T00:00:00Z',
    permissions,
    tags: [],
    preview: '',
  };
}

function render() {
  return renderWithProviders(<PromoteDialog link={readingLink()} onClose={onClose} />, {
    initialEntries: ['/reading'],
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchSuggestions).mockResolvedValue([
    {
      note_id: 'n1',
      notebook_id: 'nb1',
      title: 'Index structures',
      notebook_name: 'Databases',
      passage: 'B-trees and LSM trees',
    },
  ]);
  vi.mocked(fetchNotebooks).mockResolvedValue([
    { id: 'nb1', name: 'Databases', owner_id: 'u1', permissions: ['create_notes'] },
    { id: 'nb2', name: 'Shared with me', owner_id: 'u2', permissions: ['view_notebook'] },
  ]);
  vi.mocked(promoteLink).mockResolvedValue({
    link: readingLink({ state: 'promoted' }),
    note_id: 'n9',
    notebook_id: 'nb1',
  });
});

describe('suggestions', () => {
  it('promotes to a suggested note and opens it', async () => {
    const user = userEvent.setup();
    const { router } = render();
    const suggestions = screen.getByRole('region', { name: 'Suggested notes' });
    await user.click(await within(suggestions).findByRole('button', { name: /Index structures/ }));
    await waitFor(() => expect(promoteLink).toHaveBeenCalledWith('l1', { noteId: 'n1' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/notebooks/nb1/notes/n9'));
    expect(onClose).toHaveBeenCalled();
  });

  it('says when suggestions are unavailable', async () => {
    vi.mocked(fetchSuggestions).mockRejectedValue(new ApiError(503, 'AI is disabled'));
    render();
    expect(await screen.findByText('Suggestions are not available.')).toBeInTheDocument();
  });
});

describe('search', () => {
  it('greys out notes the user can only view', async () => {
    const response: SearchResponse = {
      results: [
        {
          note: note('n2', 'Mine', ['view_note', 'update']),
          notebook: { id: 'nb1', name: 'Databases' },
          score: 1,
          title: [],
          snippets: [],
        },
        {
          note: note('n3', 'Theirs', ['view_note']),
          notebook: { id: 'nb2', name: 'Shared' },
          score: 1,
          title: [],
          snippets: [],
        },
      ],
      unknown_tags: [],
      offset: 0,
      limit: 10,
    };
    vi.mocked(searchNotes).mockResolvedValue(response);
    const user = userEvent.setup();
    render();
    await user.type(screen.getByLabelText('Search your notes'), 'trees{Enter}');
    expect(searchNotes).toHaveBeenCalledWith('trees', { offset: 0, limit: 10 });
    expect(await screen.findByRole('button', { name: /Theirs/ })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: /Mine/ }));
    await waitFor(() => expect(promoteLink).toHaveBeenCalledWith('l1', { noteId: 'n2' }));
  });
});

describe('new note', () => {
  it('offers only notebooks taking new notes and creates one', async () => {
    const user = userEvent.setup();
    render();
    const notebook = await screen.findByLabelText('Notebook');
    await screen.findByRole('option', { name: 'Databases' });
    expect(within(notebook).queryByRole('option', { name: 'Shared with me' })).toBeNull();
    expect(screen.getByLabelText('Note title')).toHaveValue('On B-trees');
    await user.click(screen.getByRole('button', { name: 'Create' }));
    await waitFor(() =>
      expect(promoteLink).toHaveBeenCalledWith('l1', { notebookId: 'nb1', title: 'On B-trees' }),
    );
  });

  it('shows why promoting failed', async () => {
    vi.mocked(promoteLink).mockRejectedValue(new ApiError(403, 'Permission denied'));
    const user = userEvent.setup();
    render();
    await screen.findByRole('option', { name: 'Databases' });
    await user.click(screen.getByRole('button', { name: 'Create' }));
    expect(await screen.findByText('Permission denied')).toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe('copy and close', () => {
  it('copies the link as markdown', async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue();
    render();
    await user.click(screen.getByRole('button', { name: 'Copy as markdown' }));
    expect(writeText).toHaveBeenCalledWith(
      '[On B-trees](https://www.example.com/btrees)\n\nB-trees keep data sorted.',
    );
    expect(await screen.findByText('Copied')).toBeInTheDocument();
    expect(promoteLink).not.toHaveBeenCalled();
  });

  it('closes with Escape', async () => {
    const user = userEvent.setup();
    render();
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });
});
