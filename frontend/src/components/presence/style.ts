/** Colours and styles shared by the presence components. */

/** A stable colour per user, readable behind white text in both themes. */
export function avatarColor(userId: string): string {
  let hash = 0;
  for (let i = 0; i < userId.length; i++) hash = (hash * 31 + userId.charCodeAt(i)) | 0;
  return `hsl(${Math.abs(hash) % 360} 60% 42%)`;
}

/** CSS that outlines the conflicted blocks; a style rule survives re-renders of the block DOM. */
export function conflictStyle(blockIds: Iterable<string>): string {
  return [...blockIds]
    .map((id) => `.note-body [data-id="${id}"] > .bn-block-content { outline: 2px solid var(--conflict, #d97706); outline-offset: 2px; border-radius: 4px; }`)
    .join('\n');
}
