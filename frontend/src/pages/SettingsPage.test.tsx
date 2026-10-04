import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SettingsPage from './SettingsPage';
import { renderWithProviders } from '../test/renderWithProviders';
import { ApiError } from '../api/client';

vi.mock('../api/auth', () => ({
  startGoogleReauth: vi.fn(),
  switchToPassword: vi.fn(),
}));

let mockProvider: 'password' | 'google' = 'google';
vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      uid: 'u1',
      email: 'a@b.com',
      firstname: 'A',
      lastname: 'B',
      invite_quota_remaining: 5,
      auth_provider: mockProvider,
    },
    logout: vi.fn(),
  }),
}));

import { startGoogleReauth, switchToPassword } from '../api/auth';
const mockStartGoogleReauth = vi.mocked(startGoogleReauth);
const mockSwitchToPassword = vi.mocked(switchToPassword);

describe('SettingsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockProvider = 'google';
  });

  it('tells a password user how to switch to Google', () => {
    mockProvider = 'password';
    renderWithProviders(<SettingsPage />, { initialEntries: ['/settings'] });
    expect(screen.getByText(/you sign in with your email and password/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /verify with google/i })).not.toBeInTheDocument();
  });

  it('asks a Google user to re-authenticate before switching', async () => {
    const user = userEvent.setup();
    const assign = vi.fn();
    vi.stubGlobal('location', { ...window.location, assign });
    mockStartGoogleReauth.mockResolvedValueOnce('https://accounts.google.com/x');
    renderWithProviders(<SettingsPage />, { initialEntries: ['/settings'] });

    expect(screen.queryByLabelText('New password')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /verify with google/i }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith('https://accounts.google.com/x'));
    vi.unstubAllGlobals();
  });

  it('shows a re-authentication error from the callback', () => {
    renderWithProviders(<SettingsPage />, {
      initialEntries: ['/settings?google_error=reauth_mismatch'],
    });
    expect(screen.getByText(/different google account/i)).toBeInTheDocument();
  });

  it('rejects mismatched passwords', async () => {
    const user = userEvent.setup();
    renderWithProviders(<SettingsPage />, { initialEntries: ['/settings?reauth=ok'] });

    await user.type(screen.getByLabelText('New password'), 'newsecret1');
    await user.type(screen.getByLabelText('Confirm password'), 'newsecret2');
    await user.click(screen.getByRole('button', { name: /switch to password/i }));

    expect(screen.getByText('Passwords do not match.')).toBeInTheDocument();
    expect(mockSwitchToPassword).not.toHaveBeenCalled();
  });

  it('switches to password after re-authentication', async () => {
    const user = userEvent.setup();
    mockSwitchToPassword.mockResolvedValueOnce({
      uid: 'u1',
      email: 'a@b.com',
      firstname: 'A',
      lastname: 'B',
      invite_quota_remaining: 5,
      auth_provider: 'password',
    });
    renderWithProviders(<SettingsPage />, { initialEntries: ['/settings?reauth=ok'] });

    await user.type(screen.getByLabelText('New password'), 'newsecret1');
    await user.type(screen.getByLabelText('Confirm password'), 'newsecret1');
    await user.click(screen.getByRole('button', { name: /switch to password/i }));

    expect(
      await screen.findByText('You now sign in with your email and password.'),
    ).toBeInTheDocument();
    expect(mockSwitchToPassword).toHaveBeenCalledWith('newsecret1');
  });

  it('asks to verify again when the re-authentication expired', async () => {
    const user = userEvent.setup();
    mockSwitchToPassword.mockRejectedValueOnce(new ApiError(403, 'Sign in again'));
    renderWithProviders(<SettingsPage />, { initialEntries: ['/settings?reauth=ok'] });

    await user.type(screen.getByLabelText('New password'), 'newsecret1');
    await user.type(screen.getByLabelText('Confirm password'), 'newsecret1');
    await user.click(screen.getByRole('button', { name: /switch to password/i }));

    expect(await screen.findByText(/verification expired/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /verify with google/i })).toBeInTheDocument();
  });
});
