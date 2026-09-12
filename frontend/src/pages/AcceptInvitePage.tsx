import { Link, useParams, useSearchParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { fetchInvitePublic } from '../api/invites';
import RegistrationForm from '../components/RegistrationForm';
import { googleAuthErrorMessage } from '../lib/googleAuthErrors';

export default function AcceptInvitePage() {
  const { inviteId } = useParams<{ inviteId: string }>();
  const [searchParams] = useSearchParams();
  const googleError = googleAuthErrorMessage(searchParams.get('google_error'));

  const { data, isLoading } = useQuery({
    queryKey: ['invites', 'public', inviteId],
    queryFn: () => fetchInvitePublic(inviteId!),
    enabled: !!inviteId,
  });

  return (
    <div className="auth-page">
      <div className="auth-card">
        <h1>Join Assistant</h1>
        {googleError && <p className="auth-error">{googleError}</p>}
        {isLoading ? (
          <p>Loading...</p>
        ) : data?.valid ? (
          <>
            <p className="auth-banner">
              You've been invited to join. Enter the email address the invite
              was sent to.
            </p>
            <RegistrationForm inviteId={inviteId} />
          </>
        ) : (
          <>
            <p className="auth-error">This invite is no longer valid.</p>
            <p className="auth-footer">
              <Link to="/login">Back to sign in</Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
