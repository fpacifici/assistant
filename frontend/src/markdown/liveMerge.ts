/**
 * Merging other people's edits into the open note.
 *
 * The open note polls the server's nodes (`useLiveNote`). `planLiveMerge`
 * compares them with the editor and decides what to do, by the same rule the
 * server applies with node versions: the first writer wins.
 *
 * - A block whose node changed, and that has no unsaved local edits, takes
 *   the new content. One that has them becomes a conflict: it keeps the
 *   local text, is not saved, and waits for the user to keep it or take the
 *   other version.
 * - A block whose node was deleted is removed, or becomes a conflict when it
 *   has unsaved edits.
 * - A node the editor has never seen is inserted after the block of the
 *   node before it on the server.
 * - A block deleted locally but not saved yet stays deleted: on the server a
 *   delete wins over an update.
 *
 * `applyLiveMerge` carries the plan out on a BlockNote editor.
 */

import type { Block, BlockNoteEditor, PartialBlock } from '@blocknote/core';
import type { NoteNode } from '../types';
import type { ServerRegistry } from './serverRegistry';

/** A block with unsaved local edits whose node someone else changed or deleted. */
export interface BlockConflict {
  nodeId: string;
  /** The server version; `payload` null means the node was deleted. */
  version: number;
  payload: string | null;
}

export type LiveOp =
  | { type: 'update'; blockId: string; node: NoteNode }
  | { type: 'remove'; blockId: string }
  /** Insert after the block of node `afterNodeId`, or first when null. */
  | { type: 'insert'; node: NoteNode; afterNodeId: string | null }
  | { type: 'conflict'; blockId: string; conflict: BlockConflict };

export interface LiveMergeInput {
  /** The note's nodes, in server order. */
  serverNodes: NoteNode[];
  /** Top-level block ids of the editor, in order. */
  blockIds: string[];
  registry: ServerRegistry;
  /** True when the block has edits not saved yet. */
  isDirty: (blockId: string) => boolean;
  conflicts: ReadonlyMap<string, BlockConflict>;
}

function deleted(nodeId: string): BlockConflict {
  return { nodeId, version: 0, payload: null };
}

function changed(node: NoteNode): BlockConflict {
  return {
    nodeId: node.id,
    version: node.version,
    payload: node.payload ?? '',
  };
}

/** The operations that bring the editor up to date with `serverNodes`. */
export function planLiveMerge({
  serverNodes,
  blockIds,
  registry,
  isDirty,
  conflicts,
}: LiveMergeInput): LiveOp[] {
  const contentNodes = serverNodes.filter((n) => n.node_type !== 'attachment');
  const byId = new Map(contentNodes.map((n) => [n.id, n]));
  const ops: LiveOp[] = [];

  for (const blockId of blockIds) {
    const state = registry.get(blockId);
    if (!state) continue;
    const node = byId.get(state.nodeId);
    const existing = conflicts.get(blockId);

    if (existing) {
      if (!node && existing.payload !== null) {
        ops.push({ type: 'conflict', blockId, conflict: deleted(state.nodeId) });
      } else if (node && node.version > existing.version) {
        ops.push({ type: 'conflict', blockId, conflict: changed(node) });
      }
      continue;
    }

    if (!node) {
      ops.push(
        isDirty(blockId)
          ? { type: 'conflict', blockId, conflict: deleted(state.nodeId) }
          : { type: 'remove', blockId },
      );
    } else if (node.version > state.version) {
      ops.push(
        isDirty(blockId)
          ? { type: 'conflict', blockId, conflict: changed(node) }
          : { type: 'update', blockId, node },
      );
    }
  }

  // Nodes the editor doesn't know, each after the closest known node before
  // it. A node whose block was deleted locally (still in the registry until
  // the next save) is known, so it is not brought back.
  const inDocument = new Set(blockIds);
  const removed = new Set(ops.flatMap((op) => (op.type === 'remove' ? [op.blockId] : [])));
  let anchor: string | null = null;
  for (const node of contentNodes) {
    const blockId = registry.blockIdForNode(node.id);
    if (blockId === undefined) {
      ops.push({ type: 'insert', node, afterNodeId: anchor });
      anchor = node.id;
    } else if (inDocument.has(blockId) && !removed.has(blockId)) {
      anchor = node.id;
    }
  }

  return ops;
}

/** The editor blocks for a node's markdown; an empty paragraph for an empty payload. */
function parseNode(editor: BlockNoteEditor, payload: string | null): PartialBlock[] {
  const parsed = editor.tryParseMarkdownToBlocks(payload ?? '');
  return parsed.length > 0 ? parsed : [{ type: 'paragraph', content: [] }];
}

function serialize(editor: BlockNoteEditor, blockId: string): string | undefined {
  const block = editor.getBlock(blockId);
  return block ? editor.blocksToMarkdownLossy([block]).trim() : undefined;
}

/** Give `blockId` the content of `payload`, keeping its id. Extra blocks go after it. */
export function replaceBlockContent(
  editor: BlockNoteEditor,
  blockId: string,
  payload: string | null,
): void {
  const [first, ...rest] = parseNode(editor, payload);
  editor.updateBlock(blockId, {
    type: first.type,
    props: first.props,
    content: first.content,
    children: first.children ?? [],
  } as PartialBlock);
  if (rest.length > 0) editor.insertBlocks(rest, blockId, 'after');
}

/** A note with nothing in it yet shows one empty paragraph that isn't on the server. */
function isPlaceholder(editor: BlockNoteEditor, registry: ServerRegistry): Block | undefined {
  const blocks = editor.document;
  if (blocks.length !== 1) return undefined;
  const [only] = blocks;
  if (registry.has(only.id)) return undefined;
  const empty = Array.isArray(only.content) && only.content.length === 0;
  return empty && only.children.length === 0 ? only : undefined;
}

/**
 * Carry out `ops` on the editor, keeping the registry and the snapshot in
 * step so applied blocks don't look edited. Returns the conflicts after the
 * merge.
 */
export function applyLiveMerge(
  editor: BlockNoteEditor,
  registry: ServerRegistry,
  snapshot: Map<string, string>,
  conflicts: ReadonlyMap<string, BlockConflict>,
  ops: LiveOp[],
): Map<string, BlockConflict> {
  // One transaction, kept out of the undo history: undoing someone else's
  // edit would save it back as ours.
  return editor.transact((tr) => {
    tr.setMeta('addToHistory', false);
    return applyOps(editor, registry, snapshot, conflicts, ops);
  });
}

function applyOps(
  editor: BlockNoteEditor,
  registry: ServerRegistry,
  snapshot: Map<string, string>,
  conflicts: ReadonlyMap<string, BlockConflict>,
  ops: LiveOp[],
): Map<string, BlockConflict> {
  const next = new Map(conflicts);
  const placeholder = ops.some((op) => op.type === 'insert')
    ? isPlaceholder(editor, registry)
    : undefined;

  for (const op of ops) {
    switch (op.type) {
      case 'update': {
        replaceBlockContent(editor, op.blockId, op.node.payload);
        registry.updateVersion(op.blockId, op.node.version);
        const text = serialize(editor, op.blockId);
        if (text !== undefined) snapshot.set(op.blockId, text);
        break;
      }
      case 'remove':
        // A document always keeps one block.
        if (editor.document.length === 1) {
          editor.replaceBlocks([op.blockId], [{ type: 'paragraph', content: [] }]);
        } else {
          editor.removeBlocks([op.blockId]);
        }
        registry.forget(op.blockId);
        snapshot.delete(op.blockId);
        break;
      case 'insert': {
        const parsed = parseNode(editor, op.node.payload);
        const anchorBlock = op.afterNodeId ? registry.blockIdForNode(op.afterNodeId) : undefined;
        const [firstBlock] = editor.document;
        const inserted = anchorBlock
          ? editor.insertBlocks(parsed, anchorBlock, 'after')
          : firstBlock
            ? editor.insertBlocks(parsed, firstBlock.id, 'before')
            : editor.replaceBlocks(editor.document, parsed).insertedBlocks;
        const [primary] = inserted;
        if (!primary) break;
        registry.set(primary.id, {
          nodeId: op.node.id,
          version: op.node.version,
          nodeType: op.node.node_type,
        });
        const text = serialize(editor, primary.id);
        if (text !== undefined) snapshot.set(primary.id, text);
        break;
      }
      case 'conflict':
        next.set(op.blockId, op.conflict);
        // The node is gone: the block is local only until the user decides.
        if (op.conflict.payload === null) registry.forget(op.blockId);
        break;
    }
  }

  if (placeholder && editor.document.length > 1) editor.removeBlocks([placeholder.id]);
  return next;
}
