import { useEffect } from 'react';
import { Link, useParams } from 'react-router';
import { useMutation } from '@tanstack/react-query';
import { confirmEmail } from '../api/auth';

export default function ConfirmEmailPage() {
  const { token } = useParams<{ token: string }>();
  const mutation = useMutation({
    mutationFn: () => confirmEmail(token!),
  });
  const { mutate } = mutation;

  useEffect(() => {
    if (token) mutate();
  }, [token, mutate]);

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Confirm your account</h1>
        {mutation.isPending || mutation.isIdle ? (
          <p>Confirming…</p>
        ) : mutation.isSuccess ? (
          <>
            <p className="auth-banner">Your account is confirmed.</p>
            <p className="auth-footer">
              <Link to="/login">Sign in</Link>
            </p>
          </>
        ) : (
          <>
            <p className="auth-error">This confirmation link is no longer valid.</p>
            <p className="auth-footer">
              <Link to="/login">Back to sign in</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
