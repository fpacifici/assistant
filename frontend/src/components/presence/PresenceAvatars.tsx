/** Round avatars with a user's first initial, for the people on a note. */

import type { ActiveUser } from '../../types';
import { avatarColor } from './style';

export function Avatar({ user }: { user: ActiveUser }) {
  return (
    <span
      className="presence-avatar"
      style={{ background: avatarColor(user.user_id) }}
      title={user.name}
      aria-label={user.name}
      role="img"
    >
      {user.initial}
    </span>
  );
}

/** The avatars of `users`; nothing when nobody else is there. */
export default function PresenceAvatars({ users, label }: { users: ActiveUser[]; label: string }) {
  if (users.length === 0) return null;
  return (
    <span className="presence-avatars" aria-label={label}>
      {users.map((user) => (
        <Avatar key={user.user_id} user={user} />
      ))}
    </span>
  );
}
