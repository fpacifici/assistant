import type { Block, BlockNoteEditor } from '@blocknote/core';
import type { NoteNode } from '../types';
import type { ServerRegistry } from './serverRegistry';

export function buildBlocksFromNodes(
  nodes: NoteNode[],
  editor: BlockNoteEditor,
  registry: ServerRegistry,
): Block[] {
  registry.clear();
  const blocks: Block[] = [];

  for (const node of nodes) {
    const payload = node.payload ?? '';
    const parsed = editor.tryParseMarkdownToBlocks(payload);
    const primaryBlock = parsed[0];
    if (!primaryBlock) continue;

    registry.set(primaryBlock.id, {
      nodeId: node.id,
      version: node.version,
      nodeType: node.node_type,
    });
    blocks.push(primaryBlock);

    if (parsed.length > 1) {
      console.warn(
        `Node ${node.id} parsed into ${parsed.length} blocks; only the first is mapped to this server node. Extra blocks will be created on next save.`,
      );
      for (let i = 1; i < parsed.length; i++) {
        blocks.push(parsed[i]);
      }
    }
  }

  return blocks;
}

export function buildSnapshot(
  blocks: Block[],
  editor: BlockNoteEditor,
): Map<string, string> {
  const snapshot = new Map<string, string>();
  for (const block of blocks) {
    snapshot.set(block.id, editor.blocksToMarkdownLossy([block]).trim());
  }
  return snapshot;
}
