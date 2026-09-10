import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RegisterPage from './RegisterPage';
import { renderWithProviders } from '../test/renderWithProviders';
import { ApiError } from '../api/client';

vi.mock('../api/auth', () => ({
  register: vi.fn(),
  resendConfirmation: vi.fn(),
}));

vi.mock('../api/invites', () => ({
  fetchInvitesConfig: vi.fn(),
}));

import { register } from '../api/auth';
import { fetchInvitesConfig } from '../api/invites';
const mockRegister = vi.mocked(register);
const mockFetchInvitesConfig = vi.mocked(fetchInvitesConfig);

const mockNavigate = vi.fn();
vi.mock('react-router', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router')>();
  return { ...mod, useNavigate: () => mockNavigate };
});

const REGISTER_RESULT = { email: 'a@b.com', confirmation_email_sent: true };

function renderRegister() {
  return renderWithProviders(<RegisterPage />);
}

async function fillAndSubmit(user: ReturnType<typeof userEvent.setup>, overrides: Record<string, string> = {}) {
  const fields = { firstname: 'Alice', lastname: 'Smith', email: 'a@b.com', password: 'password1', ...overrides };
  await user.type(screen.getByLabelText('First name'), fields.firstname);
  await user.type(screen.getByLabelText('Last name'), fields.lastname);
  await user.type(screen.getByLabelText('Email'), fields.email);
  await user.type(screen.getByLabelText('Password'), fields.password);
  await user.click(screen.getByRole('button', { name: /create account/i }));
}

describe('RegisterPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockFetchInvitesConfig.mockResolvedValue({
      registration_enabled: true,
      invites_enabled: true,
    });
  });

  it('renders all form fields and a submit button', () => {
    renderRegister();
    expect(screen.getByLabelText('First name')).toBeInTheDocument();
    expect(screen.getByLabelText('Last name')).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument();
  });

  it('calls register with the entered values, without logging in', async () => {
    const user = userEvent.setup();
    mockRegister.mockResolvedValueOnce(REGISTER_RESULT);

    renderRegister();
    await fillAndSubmit(user);

    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith({
        firstname: 'Alice', lastname: 'Smith', email: 'a@b.com', password: 'password1',
      });
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('shows a pending-confirmation panel after successful registration', async () => {
    const user = userEvent.setup();
    mockRegister.mockResolvedValueOnce(REGISTER_RESULT);

    renderRegister();
    await fillAndSubmit(user);

    expect(await screen.findByText(/we sent a confirmation link to a@b.com/i)).toBeInTheDocument();
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument();
  });

  it('shows a resend affordance when the confirmation email failed to send', async () => {
    const user = userEvent.setup();
    mockRegister.mockResolvedValueOnce({ email: 'a@b.com', confirmation_email_sent: false });

    renderRegister();
    await fillAndSubmit(user);

    expect(await screen.findByText(/failed to send/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /resend confirmation email/i })).toBeInTheDocument();
  });

  it('shows duplicate email error on 409', async () => {
    const user = userEvent.setup();
    mockRegister.mockRejectedValueOnce(new ApiError(409, 'Email already registered'));

    renderRegister();
    await fillAndSubmit(user);

    await waitFor(() => {
      expect(screen.getByText('An account with this email already exists.')).toBeInTheDocument();
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('shows generic error on unexpected failure', async () => {
    const user = userEvent.setup();
    mockRegister.mockRejectedValueOnce(new Error('network error'));

    renderRegister();
    await fillAndSubmit(user);

    await waitFor(() => {
      expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument();
    });
  });

  it('disables submit button while loading', async () => {
    const user = userEvent.setup();
    let resolve!: () => void;
    mockRegister.mockReturnValueOnce(new Promise<never>(res => { resolve = res as () => void; }));

    renderRegister();
    await fillAndSubmit(user);

    expect(screen.getByRole('button', { name: /creating account/i })).toBeDisabled();
    resolve();
  });

  it('has a link to the login page', () => {
    renderRegister();
    expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login');
  });

  it('renders an invite-only message instead of the form when registration is disabled', async () => {
    mockFetchInvitesConfig.mockResolvedValue({
      registration_enabled: false,
      invites_enabled: true,
    });

    renderRegister();

    expect(await screen.findByText(/invite-only/i)).toBeInTheDocument();
    expect(screen.queryByLabelText('Email')).not.toBeInTheDocument();
  });
});
