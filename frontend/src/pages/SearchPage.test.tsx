import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import SearchPage from './SearchPage';
import { renderWithProviders } from '../test/renderWithProviders';

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { uid: 'u1', email: 'a@b.com', firstname: 'A', lastname: 'B', invite_quota_remaining: 1 },
    logout: vi.fn(),
  }),
}));

vi.mock('../api/invites', () => ({
  fetchInvitesConfig: vi.fn().mockResolvedValue({
    registration_enabled: true,
    invites_enabled: true,
  }),
}));

vi.mock('../api/search', () => ({ searchNotes: vi.fn(), SEARCH_PAGE_SIZE: 20 }));

import { searchNotes } from '../api/search';
const mockSearchNotes = vi.mocked(searchNotes);

describe('SearchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSearchNotes.mockResolvedValue({ results: [], unknown_tags: [], offset: 0, limit: 20 });
  });

  it('on desktop, shows results for the query in the URL under the header', async () => {
    renderWithProviders(<SearchPage />, { initialEntries: ['/search?q=berlin'] });

    expect(screen.getByRole('searchbox', { name: 'Search notes' })).toHaveValue('berlin');
    expect(await screen.findByText(/no notes match/i)).toBeInTheDocument();
    expect(mockSearchNotes).toHaveBeenCalledWith('berlin', { offset: 0, limit: 20 });
  });

  it('on mobile, is a full-screen search with a focused input', async () => {
    renderWithProviders(<SearchPage />, { initialEntries: ['/search?q=berlin'], layout: 'mobile' });

    expect(screen.getByRole('heading', { name: 'Search' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back' })).toHaveAttribute('href', '/notebooks');
    expect(screen.queryByRole('link', { name: 'Search' })).not.toBeInTheDocument();
    const input = screen.getByRole('searchbox', { name: 'Search notes' });
    expect(input).toHaveValue('berlin');
    expect(input).toHaveFocus();
    expect(await screen.findByText(/no notes match/i)).toBeInTheDocument();
  });

  it('without a query, explains the syntax instead of searching', () => {
    renderWithProviders(<SearchPage />, { initialEntries: ['/search'], layout: 'mobile' });

    expect(screen.getByText(/tag:name/)).toBeInTheDocument();
    expect(mockSearchNotes).not.toHaveBeenCalled();
  });
});
