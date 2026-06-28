import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LoginPage from './LoginPage';
import { renderWithProviders } from '../test/renderWithProviders';
import { ApiError } from '../api/client';

vi.mock('../api/auth', () => ({
  login: vi.fn(),
}));

import { login } from '../api/auth';
const mockLogin = vi.mocked(login);

const mockNavigate = vi.fn();
vi.mock('react-router', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router')>();
  return { ...mod, useNavigate: () => mockNavigate };
});

function renderLogin() {
  return renderWithProviders(<LoginPage />);
}

describe('LoginPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders email, password fields and a sign in button', () => {
    renderLogin();
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
  });

  it('calls login with entered credentials on submit', async () => {
    const user = userEvent.setup();
    mockLogin.mockResolvedValueOnce({ uid: 'u1', email: 'a@b.com', firstname: 'A', lastname: 'B' });

    renderLogin();
    await user.type(screen.getByLabelText('Email'), 'a@b.com');
    await user.type(screen.getByLabelText('Password'), 'secret');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith({ email: 'a@b.com', password: 'secret' });
    });
  });

  it('navigates to /notebooks on successful login', async () => {
    const user = userEvent.setup();
    mockLogin.mockResolvedValueOnce({ uid: 'u1', email: 'a@b.com', firstname: 'A', lastname: 'B' });

    renderLogin();
    await user.type(screen.getByLabelText('Email'), 'a@b.com');
    await user.type(screen.getByLabelText('Password'), 'secret');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/notebooks'));
  });

  it('shows invalid credentials error on 401', async () => {
    const user = userEvent.setup();
    mockLogin.mockRejectedValueOnce(new ApiError(401, 'Invalid credentials'));

    renderLogin();
    await user.type(screen.getByLabelText('Email'), 'a@b.com');
    await user.type(screen.getByLabelText('Password'), 'wrong');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText('Invalid email or password.')).toBeInTheDocument();
    });
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  it('shows generic error on unexpected failure', async () => {
    const user = userEvent.setup();
    mockLogin.mockRejectedValueOnce(new Error('network error'));

    renderLogin();
    await user.type(screen.getByLabelText('Email'), 'a@b.com');
    await user.type(screen.getByLabelText('Password'), 'secret');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    await waitFor(() => {
      expect(screen.getByText('Something went wrong. Please try again.')).toBeInTheDocument();
    });
  });

  it('disables submit button while loading', async () => {
    const user = userEvent.setup();
    let resolve!: () => void;
    mockLogin.mockReturnValueOnce(
      new Promise<never>(res => { resolve = res as () => void; }),
    );

    renderLogin();
    await user.type(screen.getByLabelText('Email'), 'a@b.com');
    await user.type(screen.getByLabelText('Password'), 'secret');
    await user.click(screen.getByRole('button', { name: /sign in/i }));

    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled();
    resolve();
  });

  it('has a link to the register page', () => {
    renderLogin();
    expect(screen.getByRole('link', { name: /register/i })).toHaveAttribute('href', '/register');
  });
});
