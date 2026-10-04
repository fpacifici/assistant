import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient } from '@tanstack/react-query';
import TagEditor from './TagEditor';
import { renderWithProviders } from '../test/renderWithProviders';
import type { Note, Tag } from '../types';

vi.mock('../api/tags', () => ({
  fetchTags: vi.fn(),
  addNoteTag: vi.fn(),
  removeNoteTag: vi.fn(),
}));

import { addNoteTag, fetchTags, removeNoteTag } from '../api/tags';

const mockFetchTags = vi.mocked(fetchTags);
const mockAddNoteTag = vi.mocked(addNoteTag);
const mockRemoveNoteTag = vi.mocked(removeNoteTag);

const WORK: Tag = { id: 't-work', name: 'Work' };
const WORKOUT: Tag = { id: 't-workout', name: 'Workout' };
const HOME: Tag = { id: 't-home', name: 'home' };

function renderEditor(tags: Tag[] = [], queryClient?: QueryClient) {
  return renderWithProviders(
    <TagEditor notebookId="nb-1" noteId="note-1" tags={tags} />,
    { queryClient },
  );
}

function suggestions() {
  return screen.queryAllByRole('option').map((o) => o.textContent);
}

describe('TagEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchTags.mockResolvedValue([HOME, WORK, WORKOUT]);
  });

  // --- Chips ---

  it('renders the note tags as chips', () => {
    renderEditor([WORK, HOME]);
    const chips = within(screen.getByRole('list', { name: 'Tags' }));
    expect(chips.getByText('Work')).toBeInTheDocument();
    expect(chips.getByText('home')).toBeInTheDocument();
  });

  it('removes a tag when × is clicked', async () => {
    const user = userEvent.setup();
    mockRemoveNoteTag.mockResolvedValue(undefined);
    renderEditor([WORK]);

    await user.click(screen.getByRole('button', { name: 'Remove tag Work' }));

    await waitFor(() => expect(mockRemoveNoteTag).toHaveBeenCalledWith('nb-1', 'note-1', 't-work'));
  });

  // --- Suggestions ---

  it('filters suggestions case-insensitively as the user types', async () => {
    const user = userEvent.setup();
    renderEditor();
    await waitFor(() => expect(mockFetchTags).toHaveBeenCalled());

    await user.type(screen.getByRole('combobox', { name: 'Add tag' }), 'WOR');

    await waitFor(() => expect(suggestions()).toEqual(['Work', 'Workout', 'Create "WOR"']));
  });

  it('does not suggest tags already on the note', async () => {
    const user = userEvent.setup();
    renderEditor([WORK]);
    await waitFor(() => expect(mockFetchTags).toHaveBeenCalled());

    await user.type(screen.getByRole('combobox', { name: 'Add tag' }), 'work');

    await waitFor(() => expect(suggestions()).toEqual(['Workout']));
  });

  it('does not offer to create a tag whose name already exists', async () => {
    const user = userEvent.setup();
    renderEditor();
    await waitFor(() => expect(mockFetchTags).toHaveBeenCalled());

    await user.type(screen.getByRole('combobox', { name: 'Add tag' }), ' HOME ');

    await waitFor(() => expect(suggestions()).toEqual(['home']));
  });

  // --- Adding ---

  it('adds an existing tag by id when a suggestion is clicked', async () => {
    const user = userEvent.setup();
    mockAddNoteTag.mockResolvedValue([WORKOUT]);
    renderEditor();
    await waitFor(() => expect(mockFetchTags).toHaveBeenCalled());

    await user.type(screen.getByRole('combobox', { name: 'Add tag' }), 'out');
    await user.click(await screen.findByRole('option', { name: 'Workout' }));

    await waitFor(() =>
      expect(mockAddNoteTag).toHaveBeenCalledWith('nb-1', 'note-1', { tagId: 't-workout' }),
    );
    expect(screen.getByRole('combobox', { name: 'Add tag' })).toHaveValue('');
  });

  it('moves through suggestions with arrow keys and selects with Enter', async () => {
    const user = userEvent.setup();
    mockAddNoteTag.mockResolvedValue([WORKOUT]);
    renderEditor();
    await waitFor(() => expect(mockFetchTags).toHaveBeenCalled());

    await user.type(screen.getByRole('combobox', { name: 'Add tag' }), 'wor');
    await screen.findByRole('option', { name: 'Work' });
    await user.keyboard('{ArrowDown}{Enter}');

    await waitFor(() =>
      expect(mockAddNoteTag).toHaveBeenCalledWith('nb-1', 'note-1', { tagId: 't-workout' }),
    );
  });

  it('creates a new tag by name when Enter is pressed on an unknown name', async () => {
    const user = userEvent.setup();
    mockAddNoteTag.mockResolvedValue([{ id: 't-new', name: 'Ideas' }]);
    renderEditor();
    await waitFor(() => expect(mockFetchTags).toHaveBeenCalled());

    await user.type(screen.getByRole('combobox', { name: 'Add tag' }), '  Ideas {Enter}');

    await waitFor(() =>
      expect(mockAddNoteTag).toHaveBeenCalledWith('nb-1', 'note-1', { name: 'Ideas' }),
    );
    expect(mockFetchTags).toHaveBeenCalledTimes(2);
  });

  it('closes the suggestions on Escape', async () => {
    const user = userEvent.setup();
    renderEditor();
    await waitFor(() => expect(mockFetchTags).toHaveBeenCalled());

    await user.type(screen.getByRole('combobox', { name: 'Add tag' }), 'wor');
    await screen.findByRole('option', { name: 'Work' });
    await user.keyboard('{Escape}');

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('updates the cached note with the returned tags', async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const note = { id: 'note-1', notebook_id: 'nb-1', tags: [] } as unknown as Note;
    queryClient.setQueryData(['note', 'nb-1', 'note-1'], note);
    mockAddNoteTag.mockResolvedValue([HOME]);
    renderEditor([], queryClient);
    await waitFor(() => expect(mockFetchTags).toHaveBeenCalled());

    await user.type(screen.getByRole('combobox', { name: 'Add tag' }), 'home{Enter}');

    await waitFor(() =>
      expect(queryClient.getQueryData<Note>(['note', 'nb-1', 'note-1'])?.tags).toEqual([HOME]),
    );
  });

  it('shows the error when tagging fails', async () => {
    const user = userEvent.setup();
    mockAddNoteTag.mockRejectedValue(new Error('Tag name is too long'));
    renderEditor();
    await waitFor(() => expect(mockFetchTags).toHaveBeenCalled());

    await user.type(screen.getByRole('combobox', { name: 'Add tag' }), 'x{Enter}');

    expect(await screen.findByText('Tag name is too long')).toBeInTheDocument();
  });
});
