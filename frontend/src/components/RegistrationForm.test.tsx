import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import RegistrationForm from './RegistrationForm';
import { renderWithProviders } from '../test/renderWithProviders';

vi.mock('../api/auth', () => ({
  register: vi.fn(),
  login: vi.fn(),
}));

const mockNavigate = vi.fn();
vi.mock('react-router', async (importOriginal) => {
  const mod = await importOriginal<typeof import('react-router')>();
  return { ...mod, useNavigate: () => mockNavigate };
});

describe('RegistrationForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the password form alongside a Google sign-in button', () => {
    renderWithProviders(<RegistrationForm />);
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /continue with google/i })).toBeInTheDocument();
  });

  it("the Google button's href has no invite_id when no inviteId prop is given", () => {
    renderWithProviders(<RegistrationForm />);
    const link = screen.getByRole('link', { name: /continue with google/i });
    expect(link.getAttribute('href')).toMatch(/\/auth\/google$/);
  });

  it("the Google button's href reflects the inviteId prop", () => {
    renderWithProviders(<RegistrationForm inviteId="invite-123" />);
    const link = screen.getByRole('link', { name: /continue with google/i });
    expect(link.getAttribute('href')).toMatch(/\/auth\/google\?invite_id=invite-123$/);
  });
});
