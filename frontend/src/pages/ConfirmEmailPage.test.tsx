import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import ConfirmEmailPage from './ConfirmEmailPage';
import { renderWithProviders } from '../test/renderWithProviders';
import { Route, Routes } from 'react-router';
import { ApiError } from '../api/client';

vi.mock('../api/auth', () => ({
  confirmEmail: vi.fn(),
}));

import { confirmEmail } from '../api/auth';
const mockConfirmEmail = vi.mocked(confirmEmail);

function renderPage(token = 'tok-123') {
  return renderWithProviders(
    <Routes>
      <Route path="/confirm-email/:token" element={<ConfirmEmailPage />} />
    </Routes>,
    { initialEntries: [`/confirm-email/${token}`] },
  );
}

describe('ConfirmEmailPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a confirmed message and a login link on success', async () => {
    mockConfirmEmail.mockResolvedValueOnce(undefined);

    renderPage();

    expect(await screen.findByText(/your account is confirmed/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login');
  });

  it('shows an invalid-link message on a 404 response', async () => {
    mockConfirmEmail.mockRejectedValueOnce(new ApiError(404, 'Confirmation link is invalid or expired'));

    renderPage();

    expect(await screen.findByText(/no longer valid/i)).toBeInTheDocument();
  });
});
