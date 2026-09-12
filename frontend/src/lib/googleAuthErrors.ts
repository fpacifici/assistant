const GOOGLE_AUTH_ERROR_MESSAGES: Record<string, string> = {
  denied: 'Google sign-in was cancelled.',
  invalid_request: 'Something went wrong starting Google sign-in. Please try again.',
  invalid_state: 'Your Google sign-in session expired. Please try again.',
  google_failed: 'Google sign-in failed. Please try again.',
  unverified_email:
    "Your Google account's email isn't verified. Verify it with Google, or use a different sign-in method.",
  collision:
    'This email already has a password account. Log in with your password instead.',
  invite_email_mismatch:
    'You signed in with a different Google account than the one this invite was sent to.',
  registration_closed: 'This invite is no longer valid, or registration is currently closed.',
};

export function googleAuthErrorMessage(code: string | null): string | null {
  if (!code) return null;
  return GOOGLE_AUTH_ERROR_MESSAGES[code] ?? 'Google sign-in failed. Please try again.';
}
