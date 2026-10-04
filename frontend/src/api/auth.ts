import { apiFetch } from './client';
import type { User } from '../types';

export interface RegisterPayload {
  email: string;
  password: string;
  firstname: string;
  lastname: string;
  invite_id?: string;
}

export interface RegisterResult {
  email: string;
  confirmation_email_sent: boolean;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export function register(payload: RegisterPayload): Promise<RegisterResult> {
  return apiFetch<RegisterResult>('/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function login(payload: LoginPayload): Promise<User> {
  return apiFetch<User>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function confirmEmail(token: string): Promise<void> {
  return apiFetch<void>(`/auth/confirm-email/${token}`, { method: 'POST' });
}

export function resendConfirmation(email: string): Promise<void> {
  return apiFetch<void>('/auth/resend-confirmation', {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export function logout(): Promise<void> {
  return apiFetch<void>('/auth/logout', { method: 'POST' });
}

export function getMe(): Promise<User> {
  return apiFetch<User>('/auth/me');
}

export interface GoogleSwapInfo {
  email: string;
  /** False for an unconfirmed account: the Google sign-in alone claims it. */
  password_required: boolean;
}

/** The account a pending password → Google switch would convert (401 if none). */
export function getGoogleSwap(): Promise<GoogleSwapInfo> {
  return apiFetch<GoogleSwapInfo>('/auth/google/swap');
}

export function confirmGoogleSwap(password: string | null): Promise<User> {
  return apiFetch<User>('/auth/google/swap', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
}

export function cancelGoogleSwap(): Promise<void> {
  return apiFetch<void>('/auth/google/swap', { method: 'DELETE' });
}

/** Where to send the browser to re-authenticate the current Google user. */
export async function startGoogleReauth(): Promise<string> {
  const { authorization_url } = await apiFetch<{ authorization_url: string }>(
    '/auth/google/reauth',
    { method: 'POST' },
  );
  return authorization_url;
}

/** Replace the Google credential with a password (needs a recent re-auth). */
export function switchToPassword(password: string): Promise<User> {
  return apiFetch<User>('/auth/credentials/password', {
    method: 'POST',
    body: JSON.stringify({ password }),
  });
}
