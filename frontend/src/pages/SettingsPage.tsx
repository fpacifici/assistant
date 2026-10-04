/** Account settings: shows the sign-in method and lets a Google user switch
 * to password sign-in after re-authenticating with Google. */

import { useState } from 'react';
import { Link, useSearchParams } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { startGoogleReauth, switchToPassword } from '../api/auth';
import { ApiError } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useIsMobile } from '../layout/LayoutModeContext';
import { googleAuthErrorMessage } from '../lib/googleAuthErrors';
import MobileTopBar from '../components/MobileTopBar';

function SwitchToPasswordForm({ onSwitched }: { onSwitched: () => void }) {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const reauthenticated = searchParams.get('reauth') === 'ok';
  const googleError = googleAuthErrorMessage(searchParams.get('google_error'));
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const handleVerify = async () => {
    setError('');
    setBusy(true);
    try {
      window.location.assign(await startGoogleReauth());
    } catch {
      setError('Could not start Google sign-in. Please try again.');
      setBusy(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setBusy(true);
    try {
      await switchToPassword(password);
      setSearchParams({});
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
      onSwitched();
    } catch (err) {
      if (err instanceof ApiError && err.status === 403) {
        setSearchParams({});
        setError('Your Google verification expired. Verify again to continue.');
      } else {
        setError('Could not switch to password sign-in. Please try again.');
      }
    } finally {
      setBusy(false);
    }
  };

  if (!reauthenticated) {
    return (
      <>
        <p>
          To switch to password sign-in, first confirm it's you by signing in with
          Google again.
        </p>
        {googleError && <p className="auth-error">{googleError}</p>}
        {error && <p className="auth-error">{error}</p>}
        <button type="button" className="btn-primary" onClick={handleVerify} disabled={busy}>
          Verify with Google
        </button>
      </>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <p>
        Choose a password. Google sign-in will be removed from your account and you
        will sign in with your email and this password.
      </p>
      <div className="form-group">
        <label htmlFor="new-password">New password</label>
        <input
          id="new-password"
          type="password"
          value={password}
          onChange={e => setPassword(e.target.value)}
          required
          minLength={8}
          autoFocus
        />
      </div>
      <div className="form-group">
        <label htmlFor="confirm-password">Confirm password</label>
        <input
          id="confirm-password"
          type="password"
          value={confirm}
          onChange={e => setConfirm(e.target.value)}
          required
          minLength={8}
        />
      </div>
      {error && <p className="auth-error">{error}</p>}
      <button type="submit" className="btn-primary" disabled={busy}>
        {busy ? 'Switching…' : 'Switch to password sign-in'}
      </button>
    </form>
  );
}

export default function SettingsPage() {
  const { user } = useAuth();
  const isMobile = useIsMobile();
  const [switched, setSwitched] = useState(false);

  return (
    <>
      {isMobile && <MobileTopBar title="Settings" backTo="/notebooks" />}
      <div className="settings-page">
        {!isMobile && (
          <>
            <p>
              <Link to="/notebooks">&larr; Back to notebooks</Link>
            </p>
            <h1>Settings</h1>
          </>
        )}
        <h2>Sign-in method</h2>
        {switched && (
          <p>You now sign in with your email and password.</p>
        )}
        {!switched && user.auth_provider === 'google' && (
          <>
            <p>You sign in with Google ({user.email}).</p>
            <SwitchToPasswordForm onSwitched={() => setSwitched(true)} />
          </>
        )}
        {!switched && user.auth_provider === 'password' && (
          <p>
            You sign in with your email and password. To switch to Google sign-in,
            sign out and choose <em>Continue with Google</em> on the sign-in page.
          </p>
        )}
      </div>
    </>
  );
}
