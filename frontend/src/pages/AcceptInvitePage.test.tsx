import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AcceptInvitePage from './AcceptInvitePage';
import { renderWithProviders } from '../test/renderWithProviders';
import { Route, Routes } from 'react-router';

vi.mock('../api/invites', () => ({
  fetchInvitePublic: vi.fn(),
}));

vi.mock('../api/auth', () => ({
  register: vi.fn(),
  resendConfirmation: vi.fn(),
}));

import { fetchInvitePublic } from '../api/invites';
import { register } from '../api/auth';
const mockFetchInvitePublic = vi.mocked(fetchInvitePublic);
const mockRegister = vi.mocked(register);

const mockNavigate = vi.fn();
vi.mock('react-router', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router')>();
  return { ...mod, useNavigate: () => mockNavigate };
});

const REGISTER_RESULT = { email: 'invitee@example.com', confirmation_email_sent: true };

function renderPage(inviteId = 'invite-123') {
  return renderWithProviders(
    <Routes>
      <Route path="/invite/:inviteId" element={<AcceptInvitePage />} />
    </Routes>,
    { initialEntries: [`/invite/${inviteId}`] },
  );
}

describe('AcceptInvitePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the email field pre-filled and locked for a valid invite', async () => {
    mockFetchInvitePublic.mockResolvedValue({ valid: true, invitee_email: 'invitee@example.com' });

    renderPage();

    const emailInput = await screen.findByLabelText('Email');
    expect(emailInput).toHaveValue('invitee@example.com');
    expect(emailInput).toHaveAttribute('readonly');
  });

  it('renders the generic invalid message for an invalid invite', async () => {
    mockFetchInvitePublic.mockResolvedValue({ valid: false, invitee_email: null });

    renderPage();

    expect(await screen.findByText(/no longer valid/i)).toBeInTheDocument();
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument();
  });

  it('submits through register with the invite id and pre-filled email', async () => {
    mockFetchInvitePublic.mockResolvedValue({ valid: true, invitee_email: 'invitee@example.com' });
    mockRegister.mockResolvedValueOnce(REGISTER_RESULT);

    const user = userEvent.setup();
    renderPage('invite-123');

    await screen.findByLabelText('Email');
    await user.type(screen.getByLabelText('First name'), 'Alice');
    await user.type(screen.getByLabelText('Last name'), 'Smith');
    await user.type(screen.getByLabelText('Password'), 'password1');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith(
        expect.objectContaining({ invite_id: 'invite-123', email: 'invitee@example.com' }),
      );
    });
    expect(await screen.findByText(/we sent a confirmation link/i)).toBeInTheDocument();
  });

  it('renders the mapped message for a google_error query param alongside the form', async () => {
    mockFetchInvitePublic.mockResolvedValue({ valid: true, invitee_email: 'invitee@example.com' });

    renderWithProviders(
      <Routes>
        <Route path="/invite/:inviteId" element={<AcceptInvitePage />} />
      </Routes>,
      { initialEntries: ['/invite/invite-123?google_error=invite_email_mismatch'] },
    );

    expect(
      await screen.findByText(
        'You signed in with a different Google account than the one this invite was sent to.',
      ),
    ).toBeInTheDocument();
    expect(await screen.findByLabelText('Email')).toBeInTheDocument();
  });
});
