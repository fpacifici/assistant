import { apiFetch } from './client';
import type { Invite, InvitesConfigFlags } from '../types';

export interface InvitePublic {
  valid: boolean;
  invitee_email: string | null;
}

export function fetchInvitesConfig(): Promise<InvitesConfigFlags> {
  return apiFetch<InvitesConfigFlags>('/invites/config');
}

export function fetchInvitePublic(inviteId: string): Promise<InvitePublic> {
  return apiFetch<InvitePublic>(`/invites/${inviteId}/public`);
}

export function createInvite(invitee_email: string): Promise<Invite> {
  return apiFetch<Invite>('/invites', {
    method: 'POST',
    body: JSON.stringify({ invitee_email }),
  });
}

export function listInvites(): Promise<Invite[]> {
  return apiFetch<Invite[]>('/invites');
}

export function voidInvite(id: string): Promise<void> {
  return apiFetch<void>(`/invites/${id}`, { method: 'DELETE' });
}

export function resendInvite(id: string): Promise<Invite> {
  return apiFetch<Invite>(`/invites/${id}/resend`, { method: 'POST' });
}
