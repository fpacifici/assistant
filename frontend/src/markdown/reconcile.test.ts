import { describe, it, expect, vi, beforeEach } from 'vitest';
import { BlockList } from './blockList';
import { executeSave } from './reconcile';
import type { NoteNode } from '../types';

vi.mock('../api/nodes', () => ({
  createNode: vi.fn(),
  updateNode: vi.fn(),
  deleteNode: vi.fn(),
}));

import { createNode, updateNode, deleteNode } from '../api/nodes';

const mockCreateNode = vi.mocked(createNode);
const mockUpdateNode = vi.mocked(updateNode);
const mockDeleteNode = vi.mocked(deleteNode);

function makeServerNode(overrides: Partial<NoteNode> = {}): NoteNode {
  return {
    id: 'created-1',
    note_id: 'note-1',
    author_id: 'user-1',
    node_type: 'markdown',
    payload: '',
    block_type: 'paragraph',
    version: 1,
    update_timestamp: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('executeSave', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCreateNode.mockResolvedValue(makeServerNode());
    mockUpdateNode.mockResolvedValue(makeServerNode({ version: 2 }));
    mockDeleteNode.mockResolvedValue(undefined);
  });

  it('creates new blocks that have no server state', async () => {
    const bl = new BlockList();
    bl.buildFromText('new content');

    await executeSave('nb-1', 'note-1', bl, 'user-1');

    expect(mockCreateNode).toHaveBeenCalledOnce();
    expect(mockCreateNode).toHaveBeenCalledWith('nb-1', 'note-1', 'new content', {
      blockType: 'paragraph',
      afterNodeId: undefined,
      beforeNodeId: undefined,
      userId: 'user-1',
    });
  });

  it('updates dirty blocks that have server state', async () => {
    const bl = new BlockList();
    bl.buildFromServerNodes([
      makeServerNode({ id: 'n1', payload: 'old', version: 3 }),
    ]);
    bl.updateBlock(bl.head!, 'updated content');

    await executeSave('nb-1', 'note-1', bl, 'user-1');

    expect(mockUpdateNode).toHaveBeenCalledOnce();
    expect(mockUpdateNode).toHaveBeenCalledWith(
      'nb-1', 'note-1', 'n1', 'updated content', 3, 'paragraph',
    );
  });

  it('deletes removed blocks', async () => {
    const bl = new BlockList();
    bl.buildFromServerNodes([
      makeServerNode({ id: 'n1', payload: 'first' }),
      makeServerNode({ id: 'n2', payload: 'second' }),
    ]);
    bl.remove(bl.tail!);

    await executeSave('nb-1', 'note-1', bl, 'user-1');

    expect(mockDeleteNode).toHaveBeenCalledWith('nb-1', 'note-1', 'n2');
    expect(bl.deletedNodeIds).toEqual([]);
  });

  it('replaces text nodes with markdown nodes', async () => {
    const bl = new BlockList();
    bl.buildFromServerNodes([
      makeServerNode({ id: 'text-1', node_type: 'text', payload: 'content', block_type: null }),
    ]);
    bl.updateBlock(bl.head!, 'updated');

    await executeSave('nb-1', 'note-1', bl, 'user-1');

    expect(mockDeleteNode).toHaveBeenCalledWith('nb-1', 'note-1', 'text-1');
    expect(mockCreateNode).toHaveBeenCalled();
  });

  it('does not call APIs for clean blocks', async () => {
    const bl = new BlockList();
    bl.buildFromServerNodes([
      makeServerNode({ id: 'n1', payload: 'unchanged' }),
    ]);

    await executeSave('nb-1', 'note-1', bl, 'user-1');

    expect(mockCreateNode).not.toHaveBeenCalled();
    expect(mockUpdateNode).not.toHaveBeenCalled();
    expect(mockDeleteNode).not.toHaveBeenCalled();
  });

  it('passes correct afterNodeId for sequenced creates', async () => {
    mockCreateNode.mockResolvedValueOnce(makeServerNode({ id: 'created-1', version: 1 }));
    mockCreateNode.mockResolvedValueOnce(makeServerNode({ id: 'created-2', version: 1 }));

    const bl = new BlockList();
    bl.buildFromText('first\n\nsecond');

    await executeSave('nb-1', 'note-1', bl, 'user-1');

    expect(mockCreateNode).toHaveBeenCalledTimes(2);
    const firstCallOpts = mockCreateNode.mock.calls[0][3];
    expect(firstCallOpts.afterNodeId).toBeUndefined();

    const secondCallOpts = mockCreateNode.mock.calls[1][3];
    expect(secondCallOpts.afterNodeId).toBe('created-1');
  });

  it('updates server state on blocks after create', async () => {
    mockCreateNode.mockResolvedValue(makeServerNode({ id: 'new-id', version: 5 }));

    const bl = new BlockList();
    bl.buildFromText('new');

    await executeSave('nb-1', 'note-1', bl, 'user-1');

    const block = bl.head!;
    expect(block.serverState).toEqual({ nodeId: 'new-id', version: 5, nodeType: 'markdown' });
    expect(block.dirty).toBe(false);
  });

  it('updates version on blocks after update', async () => {
    mockUpdateNode.mockResolvedValue(makeServerNode({ version: 10 }));

    const bl = new BlockList();
    bl.buildFromServerNodes([makeServerNode({ id: 'n1', version: 3 })]);
    bl.updateBlock(bl.head!, 'changed');

    await executeSave('nb-1', 'note-1', bl, 'user-1');

    expect(bl.head!.serverState!.version).toBe(10);
    expect(bl.head!.dirty).toBe(false);
  });
});
