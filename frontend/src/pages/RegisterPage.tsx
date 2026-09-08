import { Link } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { fetchInvitesConfig } from '../api/invites';
import RegistrationForm from '../components/RegistrationForm';

export default function RegisterPage() {
  const { data: config } = useQuery({
    queryKey: ['invites', 'config'],
    queryFn: fetchInvitesConfig,
  });

  const registrationClosed = config?.registration_enabled === false;

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Create account</h1>
        {registrationClosed ? (
          <p className="auth-error">
            This system is invite-only — ask someone for an invite link.
          </p>
        ) : (
          <RegistrationForm />
        )}
        <p className="auth-footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
