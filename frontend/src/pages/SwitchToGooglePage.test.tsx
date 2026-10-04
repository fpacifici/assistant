import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SwitchToGooglePage from './SwitchToGooglePage';
import { renderWithProviders } from '../test/renderWithProviders';
import { ApiError } from '../api/client';

vi.mock('../api/auth', () => ({
  getGoogleSwap: vi.fn(),
  confirmGoogleSwap: vi.fn(),
  cancelGoogleSwap: vi.fn(),
}));

import { cancelGoogleSwap, confirmGoogleSwap, getGoogleSwap } from '../api/auth';
const mockGetGoogleSwap = vi.mocked(getGoogleSwap);
const mockConfirmGoogleSwap = vi.mocked(confirmGoogleSwap);
const mockCancelGoogleSwap = vi.mocked(cancelGoogleSwap);

const mockNavigate = vi.fn();
vi.mock('react-router', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router')>();
  return { ...mod, useNavigate: () => mockNavigate };
});

describe('SwitchToGooglePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetGoogleSwap.mockResolvedValue({ email: 'user@example.com' });
  });

  it('shows the account being switched', async () => {
    renderWithProviders(<SwitchToGooglePage />);
    expect(await screen.findByText('user@example.com')).toBeInTheDocument();
    expect(screen.getByLabelText('Current password')).toBeInTheDocument();
  });

  it('switches with the current password and goes to notebooks', async () => {
    const user = userEvent.setup();
    mockConfirmGoogleSwap.mockResolvedValueOnce({
      uid: 'u1',
      email: 'user@example.com',
      firstname: 'A',
      lastname: 'B',
      invite_quota_remaining: 5,
      auth_provider: 'google',
    });
    renderWithProviders(<SwitchToGooglePage />);

    await user.type(await screen.findByLabelText('Current password'), 'secret123');
    await user.click(screen.getByRole('button', { name: 'Switch to Google' }));

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/notebooks'));
    expect(mockConfirmGoogleSwap).toHaveBeenCalledWith('secret123');
  });

  it('shows an error for a wrong password', async () => {
    const user = userEvent.setup();
    mockConfirmGoogleSwap.mockRejectedValueOnce(new ApiError(401, 'Invalid password'));
    renderWithProviders(<SwitchToGooglePage />);

    await user.type(await screen.findByLabelText('Current password'), 'wrong');
    await user.click(screen.getByRole('button', { name: 'Switch to Google' }));

    expect(await screen.findByText('Incorrect password.')).toBeInTheDocument();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('keeps the password and returns to login on cancel', async () => {
    const user = userEvent.setup();
    mockCancelGoogleSwap.mockResolvedValueOnce();
    renderWithProviders(<SwitchToGooglePage />);

    await user.click(await screen.findByRole('button', { name: 'Keep my password' }));

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/login'));
    expect(mockCancelGoogleSwap).toHaveBeenCalled();
  });

  it('shows an expired message when there is no pending switch', async () => {
    mockGetGoogleSwap.mockRejectedValueOnce(new ApiError(401, 'No pending switch'));
    renderWithProviders(<SwitchToGooglePage />);

    expect(await screen.findByText(/this request has expired/i)).toBeInTheDocument();
    expect(screen.queryByLabelText('Current password')).not.toBeInTheDocument();
  });
});
