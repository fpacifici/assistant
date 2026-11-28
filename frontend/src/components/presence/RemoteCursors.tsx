/** Other people's carets over the note body, each with their avatar. */

import { useLayoutEffect, useState } from 'react';
import type { BlockNoteEditor } from '@blocknote/core';
import { caretBox, type CaretBox } from '../../markdown/cursors';
import type { ServerRegistry } from '../../markdown/serverRegistry';
import type { ActiveUser } from '../../types';
import { Avatar } from './PresenceAvatars';

interface Placed extends CaretBox {
  user: ActiveUser;
}

/**
 * Draws a caret for each user whose cursor is in a block of this editor.
 * `container` is the positioned element the carets are placed in; `layoutKey`
 * changes whenever the content may have moved (an edit, a merge).
 */
export default function RemoteCursors({
  editor,
  registry,
  users,
  container,
  layoutKey,
}: {
  editor: BlockNoteEditor;
  registry: ServerRegistry;
  users: ActiveUser[];
  container: HTMLElement | null;
  layoutKey: number;
}) {
  const [placed, setPlaced] = useState<Placed[]>([]);

  useLayoutEffect(() => {
    if (!container) return;
    const place = () =>
      setPlaced(
        users.flatMap((user) => {
          const box = user.cursor && caretBox(editor, registry, user.cursor, container);
          return box ? [{ ...box, user }] : [];
        }),
      );
    place();
    window.addEventListener('resize', place);
    return () => window.removeEventListener('resize', place);
  }, [editor, registry, users, container, layoutKey]);

  return (
    <div className="remote-cursors" aria-hidden="true">
      {placed.map(({ user, top, left, height }) => (
        <div
          key={user.user_id}
          className="remote-cursor"
          data-testid={`remote-cursor-${user.user_id}`}
          style={{ top, left, height, borderColor: user.color }}
        >
          <Avatar user={user} />
        </div>
      ))}
    </div>
  );
}
