import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import GoogleAuthButton from './GoogleAuthButton';

describe('GoogleAuthButton', () => {
  it('links to /auth/google with no inviteId prop', () => {
    render(<GoogleAuthButton />);
    const link = screen.getByRole('link', { name: /continue with google/i });
    expect(link.getAttribute('href')).toMatch(/\/auth\/google$/);
  });

  it('links to /auth/google?invite_id=<id> when given an inviteId', () => {
    render(<GoogleAuthButton inviteId="invite-123" />);
    const link = screen.getByRole('link', { name: /continue with google/i });
    expect(link.getAttribute('href')).toMatch(/\/auth\/google\?invite_id=invite-123$/);
  });
});
