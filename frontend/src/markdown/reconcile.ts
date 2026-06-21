/**
 * Sync engine: reconciles the in-memory BlockList with the server by walking
 * dirty/deleted blocks and issuing DELETE, CREATE, and PATCH calls in order.
 * Uses optimistic concurrency control (expected_version) on updates.
 */

import type { BlockList, BlockNode } from './blockList';
import { createNode, deleteNode, updateNode } from '../api/nodes';

export async function executeSave(
  notebookId: string,
  noteId: string,
  blockList: BlockList,
  userId: string,
): Promise<void> {
  // 1. Delete removed blocks
  for (const nodeId of blockList.deletedNodeIds) {
    await deleteNode(notebookId, noteId, nodeId);
  }
  blockList.deletedNodeIds = [];

  // 2. Delete old TEXT nodes that need to be replaced with MARKDOWN nodes
  const blocks = blockList.toArray();
  for (const block of blocks) {
    if (block.dirty && block.serverState !== null && block.serverState.nodeType === 'text') {
      await deleteNode(notebookId, noteId, block.serverState.nodeId);
      block.serverState = null;
    }
  }

  // 3. Create new blocks (in order, so afterNodeId is available)
  for (const block of blocks) {
    if (block.serverState === null) {
      const afterNodeId = findPreviousServerNodeId(block);
      const beforeNodeId = findNextServerNodeId(block);
      const created = await createNode(notebookId, noteId, block.content, {
        blockType: block.blockType,
        afterNodeId: afterNodeId ?? undefined,
        beforeNodeId: beforeNodeId ?? undefined,
        userId,
      });
      block.serverState = { nodeId: created.id, version: created.version, nodeType: 'markdown' };
      block.dirty = false;
    }
  }

  // 4. Update dirty markdown blocks
  for (const block of blocks) {
    if (block.dirty && block.serverState !== null) {
      const updated = await updateNode(
        notebookId,
        noteId,
        block.serverState.nodeId,
        block.content,
        block.serverState.version,
        block.blockType,
      );
      block.serverState.version = updated.version;
      block.dirty = false;
    }
  }
}

function findPreviousServerNodeId(block: BlockNode): string | null {
  let prev = block.prev;
  while (prev !== null) {
    if (prev.serverState) return prev.serverState.nodeId;
    prev = prev.prev;
  }
  return null;
}

function findNextServerNodeId(block: BlockNode): string | null {
  let next = block.next;
  while (next !== null) {
    if (next.serverState) return next.serverState.nodeId;
    next = next.next;
  }
  return null;
}
