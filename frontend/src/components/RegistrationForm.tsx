/** Registration form fields + submit flow, shared by RegisterPage and AcceptInvitePage. */

import { useState } from 'react';
import { Link } from 'react-router';
import { register } from '../api/auth';
import type { RegisterResult } from '../api/auth';
import { ApiError } from '../api/client';
import ResendConfirmation from './ResendConfirmation';

interface RegistrationFormProps {
  inviteId?: string;
  initialEmail?: string;
  emailLocked?: boolean;
}

export default function RegistrationForm({
  inviteId,
  initialEmail = '',
  emailLocked = false,
}: RegistrationFormProps) {
  const [form, setForm] = useState({
    email: initialEmail,
    password: '',
    firstname: '',
    lastname: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<RegisterResult | null>(null);

  const set = (field: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const registered = await register({ ...form, invite_id: inviteId });
      setResult(registered);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError('An account with this email already exists.');
      } else {
        setError('Something went wrong. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  if (result) {
    return (
      <div className="auth-pending">
        <p>We sent a confirmation link to {result.email}.</p>
        {!result.confirmation_email_sent && (
          <p className="auth-error">
            The email failed to send — try resending below.
          </p>
        )}
        <ResendConfirmation email={result.email} />
        <p className="auth-footer">
          <Link to="/login">Back to sign in</Link>
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <div className="form-row">
        <div className="form-group">
          <label htmlFor="firstname">First name</label>
          <input
            id="firstname"
            type="text"
            value={form.firstname}
            onChange={set('firstname')}
            required
            autoFocus
          />
        </div>
        <div className="form-group">
          <label htmlFor="lastname">Last name</label>
          <input
            id="lastname"
            type="text"
            value={form.lastname}
            onChange={set('lastname')}
            required
          />
        </div>
      </div>
      <div className="form-group">
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          value={form.email}
          onChange={set('email')}
          readOnly={emailLocked}
          required
        />
      </div>
      <div className="form-group">
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={form.password}
          onChange={set('password')}
          required
          minLength={8}
        />
      </div>
      {error && <p className="auth-error">{error}</p>}
      <button type="submit" disabled={loading} className="btn-primary">
        {loading ? 'Creating account…' : 'Create account'}
      </button>
    </form>
  );
}
