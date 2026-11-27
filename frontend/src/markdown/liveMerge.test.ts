import { describe, it, expect, beforeEach } from 'vitest';
import { BlockNoteEditor } from '@blocknote/core';
import { applyLiveMerge, planLiveMerge, type BlockConflict, type LiveOp } from './liveMerge';
import { buildBlocksFromNodes, buildSnapshot } from './mapper';
import { ServerRegistry } from './serverRegistry';
import type { NoteNode } from '../types';

const node = (id: string, payload: string, version = 1): NoteNode => ({
  id,
  note_id: 'note-1',
  author_id: 'user-1',
  node_type: 'markdown',
  payload,
  block_type: 'paragraph',
  version,
  update_timestamp: '2026-11-27T00:00:00Z',
});

// --- planLiveMerge (pure) ---

describe('planLiveMerge', () => {
  let registry: ServerRegistry;
  const noConflicts = new Map<string, BlockConflict>();

  beforeEach(() => {
    registry = new ServerRegistry();
    registry.set('b1', { nodeId: 'n1', version: 1, nodeType: 'markdown' });
    registry.set('b2', { nodeId: 'n2', version: 1, nodeType: 'markdown' });
  });

  const plan = (
    serverNodes: NoteNode[],
    {
      blockIds = ['b1', 'b2'],
      dirty = [] as string[],
      conflicts = noConflicts as ReadonlyMap<string, BlockConflict>,
    } = {},
  ): LiveOp[] =>
    planLiveMerge({
      serverNodes,
      blockIds,
      registry,
      isDirty: (id) => dirty.includes(id),
      conflicts,
    });

  it('does nothing when the server has the versions the editor has', () => {
    expect(plan([node('n1', 'a'), node('n2', 'b')])).toEqual([]);
  });

  it('updates a clean block whose node has a newer version', () => {
    const changed = node('n2', 'new', 2);
    expect(plan([node('n1', 'a'), changed])).toEqual([
      { type: 'update', blockId: 'b2', node: changed },
    ]);
  });

  it('turns a newer version of an edited block into a conflict', () => {
    expect(plan([node('n1', 'a'), node('n2', 'theirs', 3)], { dirty: ['b2'] })).toEqual([
      { type: 'conflict', blockId: 'b2', conflict: { nodeId: 'n2', version: 3, payload: 'theirs' } },
    ]);
  });

  it('ignores versions older than the one the editor has', () => {
    registry.updateVersion('b1', 5);
    expect(plan([node('n1', 'old', 4), node('n2', 'b')])).toEqual([]);
  });

  it('removes a clean block whose node is gone', () => {
    expect(plan([node('n1', 'a')])).toEqual([{ type: 'remove', blockId: 'b2' }]);
  });

  it('turns a deleted node of an edited block into a conflict', () => {
    expect(plan([node('n1', 'a')], { dirty: ['b2'] })).toEqual([
      { type: 'conflict', blockId: 'b2', conflict: { nodeId: 'n2', version: 0, payload: null } },
    ]);
  });

  it('inserts unknown nodes after the closest known node before them', () => {
    const x = node('nx', 'x');
    const y = node('ny', 'y');
    const z = node('nz', 'z');
    expect(plan([z, node('n1', 'a'), x, y, node('n2', 'b')])).toEqual([
      { type: 'insert', node: z, afterNodeId: null },
      { type: 'insert', node: x, afterNodeId: 'n1' },
      { type: 'insert', node: y, afterNodeId: 'nx' },
    ]);
  });

  it('does not anchor an insert on a block it removes', () => {
    const x = node('nx', 'x');
    // n2 is gone; x came after it.
    expect(plan([node('n1', 'a'), x], { blockIds: ['b1', 'b2'] })).toEqual([
      { type: 'remove', blockId: 'b2' },
      { type: 'insert', node: x, afterNodeId: 'n1' },
    ]);
  });

  it('keeps a block deleted locally but not saved yet deleted', () => {
    // b2 is still in the registry (the save hasn't run) but not in the document.
    expect(plan([node('n1', 'a'), node('n2', 'theirs', 2)], { blockIds: ['b1'] })).toEqual([]);
  });

  it('ignores attachment nodes', () => {
    const attachment = { ...node('na', ''), node_type: 'attachment' };
    expect(plan([node('n1', 'a'), node('n2', 'b'), attachment])).toEqual([]);
  });

  it('updates an existing conflict when their version moves on', () => {
    const conflicts = new Map([['b2', { nodeId: 'n2', version: 2, payload: 'v2' }]]);
    expect(plan([node('n1', 'a'), node('n2', 'v3', 3)], { conflicts })).toEqual([
      { type: 'conflict', blockId: 'b2', conflict: { nodeId: 'n2', version: 3, payload: 'v3' } },
    ]);
    expect(plan([node('n1', 'a'), node('n2', 'v2', 2)], { conflicts })).toEqual([]);
  });

  it('marks an existing conflict deleted when the node goes', () => {
    const conflicts = new Map([['b2', { nodeId: 'n2', version: 2, payload: 'v2' }]]);
    expect(plan([node('n1', 'a')], { conflicts })).toEqual([
      { type: 'conflict', blockId: 'b2', conflict: { nodeId: 'n2', version: 0, payload: null } },
    ]);
  });
});

// --- applyLiveMerge (real editor) ---

describe('applyLiveMerge', () => {
  let editor: BlockNoteEditor;
  let registry: ServerRegistry;
  let snapshot: Map<string, string>;

  const texts = () => editor.document.map((b) => editor.blocksToMarkdownLossy([b]).trim());

  const load = (nodes: NoteNode[]) => {
    registry = new ServerRegistry();
    const blocks = buildBlocksFromNodes(nodes, editor, registry);
    editor.replaceBlocks(editor.document, blocks);
    snapshot = buildSnapshot(editor.document, editor);
  };

  const merge = (serverNodes: NoteNode[], conflicts = new Map<string, BlockConflict>()) => {
    const ops = planLiveMerge({
      serverNodes,
      blockIds: editor.document.map((b) => b.id),
      registry,
      isDirty: (id) => {
        const block = editor.getBlock(id);
        return !!block && editor.blocksToMarkdownLossy([block]).trim() !== snapshot.get(id);
      },
      conflicts,
    });
    return applyLiveMerge(editor, registry, snapshot, conflicts, ops);
  };

  beforeEach(() => {
    editor = BlockNoteEditor.create();
    load([node('n1', 'one'), node('n2', 'two')]);
  });

  it('applies a remote update in place and keeps the block clean', () => {
    const [, second] = editor.document;

    merge([node('n1', 'one'), node('n2', 'two, edited', 2)]);

    expect(texts()).toEqual(['one', 'two, edited']);
    expect(editor.document[1].id).toBe(second.id);
    expect(registry.get(second.id)?.version).toBe(2);
    expect(snapshot.get(second.id)).toBe('two, edited');
  });

  it('inserts a remote node and maps it to its block', () => {
    merge([node('n1', 'one'), node('n3', 'between'), node('n2', 'two')]);

    expect(texts()).toEqual(['one', 'between', 'two']);
    const inserted = editor.document[1];
    expect(registry.get(inserted.id)?.nodeId).toBe('n3');
    expect(snapshot.get(inserted.id)).toBe('between');
  });

  it('removes a block whose node was deleted', () => {
    const [first] = editor.document;

    merge([node('n2', 'two')]);

    expect(texts()).toEqual(['two']);
    expect(registry.get(first.id)).toBeUndefined();
    expect(snapshot.has(first.id)).toBe(false);
  });

  it('keeps local text in a conflict', () => {
    const [, second] = editor.document;
    editor.updateBlock(second.id, { content: 'mine' });

    const conflicts = merge([node('n1', 'one'), node('n2', 'theirs', 2)]);

    expect(texts()).toEqual(['one', 'mine']);
    expect(conflicts.get(second.id)).toEqual({ nodeId: 'n2', version: 2, payload: 'theirs' });
    // Still mapped at the old version: saving it would be refused.
    expect(registry.get(second.id)?.version).toBe(1);
  });

  it('unmaps an edited block whose node was deleted', () => {
    const [, second] = editor.document;
    editor.updateBlock(second.id, { content: 'mine' });

    const conflicts = merge([node('n1', 'one')]);

    expect(texts()).toEqual(['one', 'mine']);
    expect(conflicts.get(second.id)?.payload).toBeNull();
    expect(registry.get(second.id)).toBeUndefined();
  });

  it('fills an empty note, replacing the placeholder paragraph', () => {
    editor.replaceBlocks(editor.document, [{ type: 'paragraph', content: [] }]);
    registry = new ServerRegistry();
    snapshot = new Map();

    merge([node('n1', 'first'), node('n2', 'second')]);

    expect(texts()).toEqual(['first', 'second']);
  });

  it('leaves one empty block when every node is deleted', () => {
    merge([]);

    expect(editor.document).toHaveLength(1);
    expect(texts()).toEqual(['']);
  });
});
