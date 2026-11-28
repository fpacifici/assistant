/**
 * Styles shared by the presence components. A user's colour comes from the
 * server (`ActiveUser.color`) so every viewer sees the same one.
 */

/** CSS that outlines the conflicted blocks; a style rule survives re-renders of the block DOM. */
export function conflictStyle(blockIds: Iterable<string>): string {
  return [...blockIds]
    .map((id) => `.note-body [data-id="${id}"] > .bn-block-content { outline: 2px solid var(--conflict, #d97706); outline-offset: 2px; border-radius: 4px; }`)
    .join('\n');
}
