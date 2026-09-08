/** Registration form fields + submit flow, shared by RegisterPage and AcceptInvitePage. */

import { useState } from 'react';
import { useNavigate } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { register, login } from '../api/auth';
import { ApiError } from '../api/client';

interface RegistrationFormProps {
  inviteId?: string;
}

export default function RegistrationForm({ inviteId }: RegistrationFormProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    email: '',
    password: '',
    firstname: '',
    lastname: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const set = (field: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [field]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await register({ ...form, invite_id: inviteId });
      await login({ email: form.email, password: form.password });
      queryClient.invalidateQueries({ queryKey: ['auth', 'me'] });
      navigate('/notebooks');
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
