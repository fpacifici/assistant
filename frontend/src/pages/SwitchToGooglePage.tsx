/** Offered after a Google sign-in whose email belongs to a password account:
 * confirm with the current password to switch the account to Google sign-in. */

import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { cancelGoogleSwap, confirmGoogleSwap, getGoogleSwap } from '../api/auth';
import { ApiError } from '../api/client';

export default function SwitchToGooglePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const { data: swap, isLoading, isError } = useQuery({
    queryKey: ['auth', 'google-swap'],
    queryFn: getGoogleSwap,
    retry: false,
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await confirmGoogleSwap(swap?.password_required ? password : null);
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
      navigate('/notebooks');
    } catch (err) {
      if (err instanceof ApiError && err.message === 'Invalid password') {
        setError('Incorrect password.');
      } else {
        setError('This switch can no longer be completed. Please sign in again.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleCancel = async () => {
    await cancelGoogleSwap().catch(() => undefined);
    navigate('/login');
  };

  if (isLoading) return <div className="loading">Loading...</div>;

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Switch to Google sign-in</h1>
        {isError || !swap ? (
          <>
            <p className="auth-error">
              This request has expired. Sign in with Google again to retry.
            </p>
            <p className="auth-footer">
              <Link to="/login">Back to sign in</Link>
            </p>
          </>
        ) : (
          <>
            {swap.password_required ? (
              <p>
                <strong>{swap.email}</strong> already has an account that signs in with a
                password. Switch it to Google sign-in? Your password will be removed and
                you will sign in with Google from now on.
              </p>
            ) : (
              <p>
                <strong>{swap.email}</strong> has an unconfirmed account that signs in
                with a password. Google has verified this email, so you can claim the
                account and sign in with Google from now on.
              </p>
            )}
            <form onSubmit={handleSubmit}>
              {swap.password_required && (
                <div className="form-group">
                  <label htmlFor="password">Current password</label>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    required
                    autoFocus
                  />
                </div>
              )}
              {error && <p className="auth-error">{error}</p>}
              <button type="submit" disabled={submitting} className="btn-primary">
                {submitting ? 'Switching…' : 'Switch to Google'}
              </button>
            </form>
            <button type="button" className="btn-secondary" onClick={handleCancel}>
              Keep my password
            </button>
          </>
        )}
      </div>
    </div>
  );
}
