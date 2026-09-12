/** Top-level navigation to the backend's Google OAuth flow — not a fetch(),
 * since the backend owns both ends of the round trip. */

import { apiUrl } from '../api/client';

interface GoogleAuthButtonProps {
  inviteId?: string;
}

export default function GoogleAuthButton({ inviteId }: GoogleAuthButtonProps) {
  const path = inviteId
    ? `/auth/google?invite_id=${encodeURIComponent(inviteId)}`
    : '/auth/google';
  return (
    <a href={apiUrl(path)} className="btn-google">
      Continue with Google
    </a>
  );
}
