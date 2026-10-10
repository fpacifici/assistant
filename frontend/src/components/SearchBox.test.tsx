import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SearchBox from './SearchBox';
import DesktopHeader from './DesktopHeader';
import MobileTopBar from './MobileTopBar';
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

describe('SearchBox', () => {
  it('opens the search page for the typed query', async () => {
    const user = userEvent.setup();
    const { router } = renderWithProviders(<SearchBox />, { initialEntries: ['/notebooks'] });

    await user.type(screen.getByRole('searchbox', { name: 'Search notes' }), 'berlin tag:"road trip"{Enter}');

    expect(router.state.location.pathname).toBe('/search');
    expect(new URLSearchParams(router.state.location.search).get('q')).toBe('berlin tag:"road trip"');
  });

  it('does not search for blank input', async () => {
    const user = userEvent.setup();
    const { router } = renderWithProviders(<SearchBox />, { initialEntries: ['/notebooks'] });

    await user.type(screen.getByRole('searchbox', { name: 'Search notes' }), '   {Enter}');

    expect(router.state.location.pathname).toBe('/notebooks');
  });

  it('starts from the current query', () => {
    renderWithProviders(<SearchBox initialQuery="berlin" />);

    expect(screen.getByRole('searchbox', { name: 'Search notes' })).toHaveValue('berlin');
  });
});

describe('search entry points', () => {
  it('desktop header has a search box', () => {
    renderWithProviders(<DesktopHeader />);

    expect(screen.getByRole('searchbox', { name: 'Search notes' })).toBeInTheDocument();
  });

  it('mobile top bar links to the full-screen search', () => {
    renderWithProviders(<MobileTopBar title="Notebooks" />, { layout: 'mobile' });

    expect(screen.getByRole('link', { name: 'Search' })).toHaveAttribute('href', '/search');
  });
});
