import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
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

describe('MobileTopBar', () => {
  it('renders the title and a back link', () => {
    renderWithProviders(<MobileTopBar title="My notebook" backTo="/notebooks" />, {
      layout: 'mobile',
    });
    expect(screen.getByRole('heading', { name: 'My notebook' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Back' })).toHaveAttribute('href', '/notebooks');
    expect(screen.getByRole('button', { name: 'Menu' })).toBeInTheDocument();
  });

  it('omits the back link without backTo', () => {
    renderWithProviders(<MobileTopBar title="Notebooks" />, { layout: 'mobile' });
    expect(screen.queryByRole('link', { name: 'Back' })).not.toBeInTheDocument();
  });
});
