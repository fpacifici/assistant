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
