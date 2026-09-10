import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import InvitesPage from './InvitesPage';
import { renderWithProviders } from '../test/renderWithProviders';
import { ApiError } from '../api/client';
import type { Invite } from '../types';

vi.mock('../api/invites', () => ({
  listInvites: vi.fn(),
  createInvite: vi.fn(),
  voidInvite: vi.fn(),
  resendInvite: vi.fn(),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: {
      uid: 'u1',
      email: 'a@b.com',
      firstname: 'A',
      lastname: 'B',
      invite_quota_remaining: mockQuota,
    },
    logout: vi.fn(),
  }),
}));

import { listInvites, createInvite, voidInvite, resendInvite } from '../api/invites';
const mockListInvites = vi.mocked(listInvites);
const mockCreateInvite = vi.mocked(createInvite);
const mockVoidInvite = vi.mocked(voidInvite);
const mockResendInvite = vi.mocked(resendInvite);

let mockQuota = 5;

const PENDING_INVITE: Invite = {
  id: 'inv-1',
  invitee_email: 'pending@example.com',
  state: 'pending',
  created_at: '2026-01-01T00:00:00Z',
  expires_at: '2026-01-02T00:00:00Z',
  email_sent: true,
};

const HISTORY_INVITE: Invite = {
  id: 'inv-2',
  invitee_email: 'old@example.com',
  state: 'converted',
  created_at: '2026-01-01T00:00:00Z',
  expires_at: '2026-01-02T00:00:00Z',
  email_sent: true,
};

function renderPage() {
  return renderWithProviders(<InvitesPage />);
}

describe('InvitesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockQuota = 5;
    mockListInvites.mockResolvedValue([]);
  });

  it('renders quota and pending/history tables', async () => {
    mockListInvites.mockResolvedValue([PENDING_INVITE, HISTORY_INVITE]);

    renderPage();

    expect(await screen.findByText('pending@example.com')).toBeInTheDocument();
    expect(screen.getByText(/Invite quota remaining: 5/)).toBeInTheDocument();
    expect(screen.getByText(/History \(1\)/)).toBeInTheDocument();
  });

  it('submitting the compose form calls createInvite', async () => {
    mockCreateInvite.mockResolvedValue(PENDING_INVITE);
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(mockListInvites).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText('Email address'), 'new@example.com');
    await user.click(screen.getByRole('button', { name: /send invite/i }));

    await waitFor(() => {
      expect(mockCreateInvite).toHaveBeenCalledWith('new@example.com');
    });
  });

  it('renders "no invites remaining" on a 403 response', async () => {
    mockCreateInvite.mockRejectedValueOnce(new ApiError(403, 'No invite quota remaining'));
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(mockListInvites).toHaveBeenCalled());

    await user.type(screen.getByPlaceholderText('Email address'), 'new@example.com');
    await user.click(screen.getByRole('button', { name: /send invite/i }));

    expect(await screen.findByText('No invites remaining.')).toBeInTheDocument();
  });

  it('clicking Resend calls resendInvite', async () => {
    mockListInvites.mockResolvedValue([PENDING_INVITE]);
    mockResendInvite.mockResolvedValue(PENDING_INVITE);
    const user = userEvent.setup();

    renderPage();
    await screen.findByText('pending@example.com');

    await user.click(screen.getByRole('button', { name: /resend/i }));

    await waitFor(() => {
      expect(mockResendInvite).toHaveBeenCalledWith('inv-1');
    });
  });

  it('shows a warning when a pending invite failed to send', async () => {
    mockListInvites.mockResolvedValue([{ ...PENDING_INVITE, email_sent: false }]);

    renderPage();

    expect(await screen.findByText(/email failed to send/i)).toBeInTheDocument();
  });

  it('clicking Void calls voidInvite', async () => {
    mockListInvites.mockResolvedValue([PENDING_INVITE]);
    mockVoidInvite.mockResolvedValue(undefined);
    const user = userEvent.setup();

    renderPage();
    await screen.findByText('pending@example.com');

    await user.click(screen.getByRole('button', { name: /void/i }));

    await waitFor(() => {
      expect(mockVoidInvite).toHaveBeenCalledWith('inv-1');
    });
  });

  it('disables the submit button when quota is 0', async () => {
    mockQuota = 0;
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(mockListInvites).toHaveBeenCalled());
    await user.type(screen.getByPlaceholderText('Email address'), 'new@example.com');

    expect(screen.getByRole('button', { name: /send invite/i })).toBeDisabled();
  });
});
