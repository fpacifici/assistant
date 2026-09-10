/** Send invites, see the invite quota, manage pending invites and view history. */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router';
import { createInvite, listInvites, resendInvite, voidInvite } from '../api/invites';
import { ApiError } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import type { Invite } from '../types';

export default function InvitesPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [error, setError] = useState<string | null>(null);

  const { data: invites = [], isLoading } = useQuery({
    queryKey: ['invites'],
    queryFn: listInvites,
  });

  const createMutation = useMutation({
    mutationFn: (invitee_email: string) => createInvite(invitee_email),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invites'] });
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
      setEmail('');
      setError(null);
    },
    onError: (err: unknown) => {
      setError(
        err instanceof ApiError && err.status === 403
          ? 'No invites remaining.'
          : 'Failed to send invite.',
      );
    },
  });

  const voidMutation = useMutation({
    mutationFn: (id: string) => voidInvite(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invites'] });
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
    },
  });

  const resendMutation = useMutation({
    mutationFn: (id: string) => resendInvite(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['invites'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (email.trim() && user.invite_quota_remaining > 0) {
      createMutation.mutate(email.trim());
    }
  };

  const pending = invites.filter((i) => i.state === 'pending');
  const history = invites.filter((i) => i.state !== 'pending');

  return (
    <div className="invites-page">
      <p>
        <Link to="/notebooks">&larr; Back to notebooks</Link>
      </p>
      <h1>Invites</h1>
      <p className="quota-badge">
        Invite quota remaining: {user.invite_quota_remaining}
      </p>

      <form onSubmit={handleSubmit} className="create-form">
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email address"
        />
        <button
          type="submit"
          disabled={
            !email.trim() ||
            user.invite_quota_remaining <= 0 ||
            createMutation.isPending
          }
        >
          Send invite
        </button>
      </form>
      {error && <p className="auth-error">{error}</p>}

      {isLoading ? (
        <p>Loading...</p>
      ) : (
        <>
          <h2>Pending</h2>
          <table>
            <tbody>
              {pending.map((invite) => (
                <tr key={invite.id}>
                  <td>{invite.invitee_email}</td>
                  <td>
                    {invite.email_sent === false && (
                      <span className="auth-error">Email failed to send</span>
                    )}
                  </td>
                  <td>
                    <button
                      onClick={() => resendMutation.mutate(invite.id)}
                      disabled={resendMutation.isPending}
                    >
                      Resend
                    </button>
                  </td>
                  <td>
                    <button onClick={() => voidMutation.mutate(invite.id)}>
                      Void
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {pending.length === 0 && <p className="empty">No pending invites</p>}

          <details>
            <summary>History ({history.length})</summary>
            <table>
              <tbody>
                {history.map((invite) => (
                  <HistoryRow key={invite.id} invite={invite} />
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </div>
  );
}

function HistoryRow({ invite }: { invite: Invite }) {
  return (
    <tr>
      <td>{invite.invitee_email}</td>
      <td>{invite.state}</td>
    </tr>
  );
}
