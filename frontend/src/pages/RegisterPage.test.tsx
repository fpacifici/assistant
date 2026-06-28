import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RegisterPage from './RegisterPage';
import { renderWithProviders } from '../test/renderWithProviders';
import { ApiError } from '../api/client';

vi.mock('../api/auth', () => ({
  register: vi.fn(),
  login: vi.fn(),
}));

import { register, login } from '../api/auth';
const mockRegister = vi.mocked(register);
const mockLogin = vi.mocked(login);

const mockNavigate = vi.fn();
vi.mock('react-router', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router')>();
  return { ...mod, useNavigate: () => mockNavigate };
});

const USER = { uid: 'u1', email: 'a@b.com', firstname: 'Alice', lastname: 'Smith' };

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
  });

  it('renders all form fields and a submit button', () => {
    renderRegister();
    expect(screen.getByLabelText('First name')).toBeInTheDocument();
    expect(screen.getByLabelText('Last name')).toBeInTheDocument();
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /create account/i })).toBeInTheDocument();
  });

  it('calls register then login with the entered values', async () => {
    const user = userEvent.setup();
    mockRegister.mockResolvedValueOnce(USER);
    mockLogin.mockResolvedValueOnce(USER);

    renderRegister();
    await fillAndSubmit(user);

    await waitFor(() => {
      expect(mockRegister).toHaveBeenCalledWith({
        firstname: 'Alice', lastname: 'Smith', email: 'a@b.com', password: 'password1',
      });
    });
    expect(mockLogin).toHaveBeenCalledWith({ email: 'a@b.com', password: 'password1' });
  });

  it('navigates to /notebooks after successful registration', async () => {
    const user = userEvent.setup();
    mockRegister.mockResolvedValueOnce(USER);
    mockLogin.mockResolvedValueOnce(USER);

    renderRegister();
    await fillAndSubmit(user);

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/notebooks'));
  });

  it('shows duplicate email error on 409', async () => {
    const user = userEvent.setup();
    mockRegister.mockRejectedValueOnce(new ApiError(409, 'Email already registered'));

    renderRegister();
    await fillAndSubmit(user);

    await waitFor(() => {
      expect(screen.getByText('An account with this email already exists.')).toBeInTheDocument();
    });
    expect(mockLogin).not.toHaveBeenCalled();
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
});
