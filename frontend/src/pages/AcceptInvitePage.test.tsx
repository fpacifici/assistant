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
  login: vi.fn(),
}));

import { fetchInvitePublic } from '../api/invites';
import { register, login } from '../api/auth';
const mockFetchInvitePublic = vi.mocked(fetchInvitePublic);
const mockRegister = vi.mocked(register);
const mockLogin = vi.mocked(login);

const mockNavigate = vi.fn();
vi.mock('react-router', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router')>();
  return { ...mod, useNavigate: () => mockNavigate };
});

const USER = {
  uid: 'u1',
  email: 'invitee@example.com',
  firstname: 'Alice',
  lastname: 'Smith',
  invite_quota_remaining: 5,
};

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

  it('renders an editable, empty email field for a valid invite (never prefilled)', async () => {
    mockFetchInvitePublic.mockResolvedValue({ valid: true });

    renderPage();

    const emailInput = await screen.findByLabelText('Email');
    expect(emailInput).toHaveValue('');
    expect(emailInput).not.toHaveAttribute('readonly');
  });

  it('renders the generic invalid message for an invalid invite', async () => {
    mockFetchInvitePublic.mockResolvedValue({ valid: false });

    renderPage();

    expect(await screen.findByText(/no longer valid/i)).toBeInTheDocument();
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument();
  });

  it('submits through register with the typed email and invite id, and navigates on success', async () => {
    mockFetchInvitePublic.mockResolvedValue({ valid: true });
    mockRegister.mockResolvedValueOnce(USER);
    mockLogin.mockResolvedValueOnce(USER);

    const user = userEvent.setup();
    renderPage('invite-123');

    await screen.findByLabelText('Email');
    await user.type(screen.getByLabelText('First name'), 'Alice');
    await user.type(screen.getByLabelText('Last name'), 'Smith');
    await user.type(screen.getByLabelText('Email'), 'invitee@example.com');
    await user.type(screen.getByLabelText('Password'), 'password1');
    await user.click(screen.getByRole('button', { name: /create account/i }));

    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith(
        expect.objectContaining({ invite_id: 'invite-123', email: 'invitee@example.com' }),
      );
    });
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/notebooks'));
  });

  it('renders the mapped message for a google_error query param alongside the form', async () => {
    mockFetchInvitePublic.mockResolvedValue({ valid: true });

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
