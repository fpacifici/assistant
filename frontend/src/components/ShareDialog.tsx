/** Modal dialog for sharing a notebook or note: list current entitlements, grant a new one, revoke one. */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchNotebookEntitlements,
  shareNotebook,
  revokeNotebookEntitlement,
} from '../api/notebooks';
import { fetchNoteEntitlements, shareNote, revokeNoteEntitlement } from '../api/notes';
import { ApiError } from '../api/client';

interface ShareDialogProps {
  subjectType: 'notebook' | 'note';
  notebookId: string;
  noteId?: string;
  roleOptions: string[];
  onClose: () => void;
}

export default function ShareDialog({
  subjectType,
  notebookId,
  noteId,
  roleOptions,
  onClose,
}: ShareDialogProps) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [role, setRole] = useState(roleOptions[0] ?? '');
  const [error, setError] = useState<string | null>(null);

  const isNote = subjectType === 'note';
  const queryKey = isNote
    ? ['note-entitlements', notebookId, noteId]
    : ['notebook-entitlements', notebookId];

  const { data: entitlements = [], isLoading } = useQuery({
    queryKey,
    queryFn: () =>
      isNote
        ? fetchNoteEntitlements(notebookId, noteId!)
        : fetchNotebookEntitlements(notebookId),
  });

  const shareMutation = useMutation({
    mutationFn: () =>
      isNote
        ? shareNote(notebookId, noteId!, email, role)
        : shareNotebook(notebookId, email, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      setEmail('');
      setError(null);
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : 'Failed to share');
    },
  });

  const revokeMutation = useMutation({
    mutationFn: (entitlementId: string) =>
      isNote
        ? revokeNoteEntitlement(notebookId, noteId!, entitlementId)
        : revokeNotebookEntitlement(notebookId, entitlementId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
    },
    onError: (err: unknown) => {
      setError(err instanceof ApiError ? err.message : 'Failed to revoke');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (email.trim() && role) shareMutation.mutate();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Share {subjectType}</h3>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>

        <form onSubmit={handleSubmit} className="share-form">
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email address"
          />
          <select value={role} onChange={(e) => setRole(e.target.value)}>
            {roleOptions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
          <button type="submit" disabled={!email.trim() || shareMutation.isPending}>
            Share
          </button>
        </form>
        {error && <p className="share-error">{error}</p>}

        {isLoading ? (
          <p>Loading...</p>
        ) : (
          <ul className="entitlement-list">
            {entitlements.map((ent) => (
              <li key={ent.id} className="entitlement-item">
                <span className="entitlement-email">{ent.principal_email}</span>
                <span className="entitlement-role">{ent.role}</span>
                <button
                  className="delete-btn"
                  onClick={() => revokeMutation.mutate(ent.id)}
                  title="Revoke"
                >
                  x
                </button>
              </li>
            ))}
            {entitlements.length === 0 && <p className="empty">Not shared with anyone</p>}
          </ul>
        )}
      </div>
    </div>
  );
}
