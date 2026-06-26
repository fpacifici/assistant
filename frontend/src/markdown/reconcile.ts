import type { Block, BlockNoteEditor } from '@blocknote/core';
import { createNode, deleteNode, updateNode } from '../api/nodes';
import type { ServerRegistry } from './serverRegistry';

const BLOCKNOTE_TO_SERVER_BLOCK_TYPE: Record<string, string> = {
  paragraph: 'paragraph',
  heading: 'heading',
  bulletListItem: 'list_item',
  numberedListItem: 'list_item',
  checkListItem: 'list_item',
  codeBlock: 'code_block',
  quote: 'blockquote',
  image: 'image',
};

function toServerBlockType(blockNoteType: string): string {
  return BLOCKNOTE_TO_SERVER_BLOCK_TYPE[blockNoteType] ?? 'paragraph';
}

export async function executeSave(
  notebookId: string,
  noteId: string,
  editor: BlockNoteEditor,
  registry: ServerRegistry,
  snapshot: Map<string, string>,
  userId: string,
): Promise<Map<string, string>> {
  const currentBlocks = editor.document;
  const currentIds = new Set(currentBlocks.map((b) => b.id));

  // 1. Mark blocks removed from the document as deleted
  for (const [blockId] of snapshot) {
    if (!currentIds.has(blockId)) {
      registry.markDeleted(blockId);
    }
  }

  // 2. Delete server nodes for removed blocks
  for (const nodeId of registry.consumeDeletedIds()) {
    await deleteNode(notebookId, noteId, nodeId);
  }

  // 3. Create new blocks and update changed blocks in document order
  for (let i = 0; i < currentBlocks.length; i++) {
    const block = currentBlocks[i];
    const serialized = editor.blocksToMarkdownLossy([block]).trim();
    const state = registry.get(block.id);

    const serverBlockType = toServerBlockType(block.type);

    if (!state) {
      const created = await createNode(notebookId, noteId, serialized, {
        blockType: serverBlockType,
        afterNodeId: findAfterNodeId(currentBlocks, i, registry),
        beforeNodeId: findBeforeNodeId(currentBlocks, i, registry),
        userId,
      });
      registry.set(block.id, {
        nodeId: created.id,
        version: created.version,
        nodeType: 'markdown',
      });
    } else if (state.nodeType === 'text') {
      // Migrate legacy TEXT node to markdown
      await deleteNode(notebookId, noteId, state.nodeId);
      const created = await createNode(notebookId, noteId, serialized, {
        blockType: serverBlockType,
        afterNodeId: findAfterNodeId(currentBlocks, i, registry),
        beforeNodeId: findBeforeNodeId(currentBlocks, i, registry),
        userId,
      });
      registry.set(block.id, {
        nodeId: created.id,
        version: created.version,
        nodeType: 'markdown',
      });
    } else {
      const previousSerialized = snapshot.get(block.id);
      if (previousSerialized !== undefined && previousSerialized !== serialized) {
        const updated = await updateNode(
          notebookId,
          noteId,
          state.nodeId,
          serialized,
          state.version,
          serverBlockType,
        );
        registry.updateVersion(block.id, updated.version);
      }
    }
  }

  // Return updated snapshot
  const newSnapshot = new Map<string, string>();
  for (const block of currentBlocks) {
    newSnapshot.set(block.id, editor.blocksToMarkdownLossy([block]).trim());
  }
  return newSnapshot;
}

function findAfterNodeId(
  blocks: Block[],
  index: number,
  registry: ServerRegistry,
): string | undefined {
  for (let i = index - 1; i >= 0; i--) {
    const state = registry.get(blocks[i].id);
    if (state) return state.nodeId;
  }
  return undefined;
}

function findBeforeNodeId(
  blocks: Block[],
  index: number,
  registry: ServerRegistry,
): string | undefined {
  for (let i = index + 1; i < blocks.length; i++) {
    const state = registry.get(blocks[i].id);
    if (state) return state.nodeId;
  }
  return undefined;
}
