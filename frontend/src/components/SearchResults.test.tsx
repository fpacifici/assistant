import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SearchResults from './SearchResults';
import { renderWithProviders } from '../test/renderWithProviders';
import type { SearchResponse, SearchResult } from '../types';

vi.mock('../api/search', () => ({ searchNotes: vi.fn(), SEARCH_PAGE_SIZE: 20 }));

import { searchNotes } from '../api/search';
const mockSearchNotes = vi.mocked(searchNotes);

function result(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    note: {
      id: 'n1',
      notebook_id: 'nb1',
      owner_id: 'u1',
      title: 'Trip to Berlin',
      creation_timestamp: '2026-10-01T00:00:00Z',
      update_timestamp: '2026-10-02T00:00:00Z',
      permissions: ['view_note'],
      tags: [{ id: 't1', name: 'travel' }],
    },
    notebook: { id: 'nb1', name: 'Travel' },
    score: 0.5,
    title: [
      { text: 'Trip to ', highlighted: false },
      { text: 'Berlin', highlighted: true },
    ],
    snippets: [
      {
        node_id: 'node1',
        segments: [
          { text: 'Fly to ', highlighted: false },
          { text: 'Berlin', highlighted: true },
        ],
      },
    ],
    ...overrides,
  };
}

function page(results: SearchResult[], extra: Partial<SearchResponse> = {}): SearchResponse {
  return { results, unknown_tags: [], offset: 0, limit: 20, ...extra };
}

describe('SearchResults', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows each note with its notebook, tags and highlighted snippets', async () => {
    mockSearchNotes.mockResolvedValueOnce(page([result()]));
    renderWithProviders(<SearchResults query="berlin" />);

    const item = await screen.findByRole('listitem');
    expect(within(item).getByText('Travel')).toBeInTheDocument();
    expect(within(item).getByText('travel')).toBeInTheDocument();
    const marks = item.querySelectorAll('mark');
    expect([...marks].map((m) => m.textContent)).toEqual(['Berlin', 'Berlin']);
    expect(mockSearchNotes).toHaveBeenCalledWith('berlin', { offset: 0, limit: 20 });
  });

  it('renders snippet text as text, never as HTML', async () => {
    mockSearchNotes.mockResolvedValueOnce(
      page([
        result({
          snippets: [
            { node_id: 'node1', segments: [{ text: '<img src=x onerror=alert(1)>', highlighted: true }] },
          ],
        }),
      ]),
    );
    renderWithProviders(<SearchResults query="img" />);

    expect(await screen.findByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
  });

  it('links each snippet to its block in the note', async () => {
    mockSearchNotes.mockResolvedValueOnce(page([result()]));
    renderWithProviders(<SearchResults query="berlin" />);

    await screen.findByRole('listitem');
    const links = screen.getAllByRole('link').map((a) => [a.textContent, a.getAttribute('href')]);
    expect(links).toEqual([
      ['Trip to Berlin', '/notebooks/nb1/notes/n1?node=node1'],
      ['Fly to Berlin', '/notebooks/nb1/notes/n1?node=node1'],
    ]);
  });

  it('says when nothing matches', async () => {
    mockSearchNotes.mockResolvedValueOnce(page([]));
    renderWithProviders(<SearchResults query="nothing" />);

    expect(await screen.findByText(/no notes match/i)).toBeInTheDocument();
  });

  it('explains unknown tags', async () => {
    mockSearchNotes.mockResolvedValueOnce(page([], { unknown_tags: ['work'] }));
    renderWithProviders(<SearchResults query="tag:work" />);

    expect(await screen.findByText(/you have no tag “work”/i)).toBeInTheDocument();
  });

  it('loads more results on request', async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 20 }, (_, i) =>
      result({ note: { ...result().note, id: `n${i}` } }),
    );
    mockSearchNotes
      .mockResolvedValueOnce(page(many))
      .mockResolvedValueOnce(page([result({ note: { ...result().note, id: 'last' } })], { offset: 20 }));
    renderWithProviders(<SearchResults query="berlin" />);

    await user.click(await screen.findByRole('button', { name: /load more/i }));

    expect(await screen.findAllByRole('listitem')).toHaveLength(21);
    expect(mockSearchNotes).toHaveBeenLastCalledWith('berlin', { offset: 20, limit: 20 });
    expect(screen.queryByRole('button', { name: /load more/i })).not.toBeInTheDocument();
  });
});
