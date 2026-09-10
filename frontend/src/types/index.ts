export interface User {
  uid: string;
  email: string;
  firstname: string;
  lastname: string;
  invite_quota_remaining: number;
}

export interface Invite {
  id: string;
  invitee_email: string;
  state: 'pending' | 'void' | 'converted';
  created_at: string;
  expires_at: string;
  email_sent?: boolean;
}

export interface InvitesConfigFlags {
  registration_enabled: boolean;
  invites_enabled: boolean;
}

export interface Notebook {
  id: string;
  name: string;
  owner_id: string;
  permissions: string[];
}

export interface Note {
  id: string;
  notebook_id: string;
  owner_id: string;
  title: string;
  creation_timestamp: string;
  update_timestamp: string;
  permissions: string[];
}

export interface Entitlement {
  id: string;
  principal_id: string;
  principal_email: string;
  role: string;
  created_at: string;
}

export interface NoteNode {
  id: string;
  note_id: string;
  author_id: string;
  node_type: string;
  payload: string | null;
  block_type: string | null;
  version: number;
  update_timestamp: string;
}
