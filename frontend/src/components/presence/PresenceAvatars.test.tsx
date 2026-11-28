import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import PresenceAvatars from './PresenceAvatars';

describe('PresenceAvatars', () => {
  it('paints each avatar with the colour the server sent', () => {
    render(
      <PresenceAvatars
        label="Also on this note"
        users={[{ user_id: 'u2', name: 'Leda', initial: 'L', color: '#ab2b76', cursor: null }]}
      />,
    );

    expect(screen.getByRole('img', { name: 'Leda' })).toHaveStyle({ background: '#ab2b76' });
  });
});
