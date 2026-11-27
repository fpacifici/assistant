/**
 * Carets as `(server node, character offset)`, so they mean the same thing
 * in every editor that has the note open.
 */

import type { BlockNoteEditor } from '@blocknote/core';
import type { PresenceCursor } from '../types';
import type { ServerRegistry } from './serverRegistry';

type PMNode = BlockNoteEditor['prosemirrorState']['doc'];

interface BlockContent {
  /** Document position where the block's text starts. */
  start: number;
  /** Length of the block's text. */
  size: number;
}

/** Where the text of top-level block `blockId` sits in the ProseMirror document. */
function findBlockContent(doc: PMNode, blockId: string): BlockContent | null {
  let found: BlockContent | null = null;
  doc.descendants((node, pos) => {
    if (found) return false;
    if (node.type.name === 'blockContainer' && node.attrs.id === blockId) {
      const content = node.firstChild;
      // blockContainer opens at `pos`, its blockContent at `pos + 1`.
      found = { start: pos + 2, size: content?.content.size ?? 0 };
      return false;
    }
    return true;
  });
  return found;
}

/** The local caret, or null when it isn't in a block saved on the server. */
export function localCursor(
  editor: BlockNoteEditor,
  registry: ServerRegistry,
): PresenceCursor | null {
  try {
    const blockId = editor.getTextCursorPosition().block.id;
    const state = registry.get(blockId);
    if (!state) return null;
    const pmState = editor.prosemirrorState;
    const content = findBlockContent(pmState.doc, blockId);
    if (!content) return null;
    const offset = Math.min(Math.max(pmState.selection.head - content.start, 0), content.size);
    return { node_id: state.nodeId, offset };
  } catch {
    return null;
  }
}

export interface CaretBox {
  top: number;
  left: number;
  height: number;
}

/**
 * Where a remote caret goes, in the content coordinates of `container` (a
 * positioned element, possibly scrolling), so the caret scrolls with the
 * text. Falls back to the
 * block's left edge when the exact spot can't be measured; null when its
 * block is not in this editor.
 */
export function caretBox(
  editor: BlockNoteEditor,
  registry: ServerRegistry,
  cursor: PresenceCursor,
  container: HTMLElement,
): CaretBox | null {
  const blockId = registry.blockIdForNode(cursor.node_id);
  if (!blockId) return null;
  const rect0 = container.getBoundingClientRect();
  const origin = {
    top: rect0.top - container.scrollTop,
    left: rect0.left - container.scrollLeft,
  };
  try {
    const view = editor.prosemirrorView;
    const content = findBlockContent(view.state.doc, blockId);
    if (content) {
      const coords = view.coordsAtPos(content.start + Math.min(cursor.offset, content.size));
      return {
        top: coords.top - origin.top,
        left: coords.left - origin.left,
        height: Math.max(coords.bottom - coords.top, 16),
      };
    }
  } catch {
    // Not laid out (e.g. jsdom): use the block instead.
  }
  const element = container.querySelector<HTMLElement>(`[data-id="${blockId}"]`);
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  return {
    top: rect.top - origin.top,
    left: rect.left - origin.left,
    height: Math.max(rect.height, 16),
  };
}
