/** Resend-confirmation-email button + status message, shared by RegistrationForm and LoginPage. */

import { useState } from 'react';
import { resendConfirmation } from '../api/auth';
import { ApiError } from '../api/client';

interface ResendConfirmationProps {
  email: string;
}

export default function ResendConfirmation({ email }: ResendConfirmationProps) {
  const [status, setStatus] = useState<'idle' | 'sending' | 'sent'>('idle');
  const [error, setError] = useState('');

  const handleResend = async () => {
    setStatus('sending');
    setError('');
    try {
      await resendConfirmation(email);
      setStatus('sent');
    } catch (err) {
      setStatus('idle');
      if (err instanceof ApiError && err.status === 404) {
        setError('No pending registration for this email.');
      } else if (err instanceof ApiError && err.status === 429) {
        setError('A confirmation email was sent recently — please wait a few minutes.');
      } else if (err instanceof ApiError && err.status === 403) {
        setError('Too many attempts — please register again.');
      } else {
        setError('Something went wrong. Please try again.');
      }
    }
  };

  if (status === 'sent') {
    return <p className="auth-banner">Confirmation email sent — check your inbox.</p>;
  }

  return (
    <div className="resend-confirmation">
      <button
        type="button"
        onClick={handleResend}
        disabled={status === 'sending'}
        className="btn-secondary"
      >
        {status === 'sending' ? 'Sending…' : 'Resend confirmation email'}
      </button>
      {error && <p className="auth-error">{error}</p>}
    </div>
  );
}
