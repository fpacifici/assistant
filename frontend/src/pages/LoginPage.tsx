import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { login } from '../api/auth';
import { ApiError } from '../api/client';
import ResendConfirmation from '../components/ResendConfirmation';

export default function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [notConfirmed, setNotConfirmed] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setNotConfirmed(false);
    setLoading(true);
    try {
      await login({ email, password });
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
      navigate('/notebooks');
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        setError('Invalid email or password.');
      } else if (err instanceof ApiError && err.status === 403) {
        setNotConfirmed(true);
      } else {
        setError('Something went wrong. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Sign in</h1>
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
          </div>
          {error && <p className="auth-error">{error}</p>}
          {notConfirmed && (
            <>
              <p className="auth-error">
                Account not confirmed — check your email or request a new link.
              </p>
              <ResendConfirmation email={email} />
            </>
          )}
          <button type="submit" disabled={loading} className="btn-primary">
            {loading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="auth-footer">
          Don't have an account? <Link to="/register">Register</Link>
        </p>
      </div>
    </div>
  );
}
