import { describe, it, expect, beforeEach, vi } from 'vitest';
import { executeSave } from './reconcile';
import { ServerRegistry } from './serverRegistry';
import type { Block, BlockNoteEditor } from '@blocknote/core';
import type { NoteNode } from '../types';

vi.mock('../api/nodes', () => ({
  createNode: vi.fn(),
  deleteNode: vi.fn(),
  updateNode: vi.fn(),
}));

import { createNode, deleteNode, updateNode } from '../api/nodes';

const mockCreate = vi.mocked(createNode);
const mockDelete = vi.mocked(deleteNode);
const mockUpdate = vi.mocked(updateNode);

// --- helpers ---

const makeBlock = (id: string, type = 'paragraph'): Block =>
  ({ id, type, props: {}, content: [], children: [] }) as unknown as Block;

const makeNode = (id: string, version = 1): NoteNode => ({
  id,
  note_id: 'note-1',
  author_id: 'user-1',
  node_type: 'markdown',
  payload: 'text',
  block_type: 'paragraph',
  version,
  update_timestamp: '2024-01-01T00:00:00Z',
});

function makeEditor(blocks: Block[], serializer?: (b: Block[]) => string): BlockNoteEditor {
  return {
    document: blocks,
    blocksToMarkdownLossy: vi.fn((bs: Block[]) =>
      serializer ? serializer(bs) : (bs[0]?.id ?? '') + ' content',
    ),
  } as unknown as BlockNoteEditor;
}

// Consistent serializer keyed by block id
const serialize = (bs: Block[]) => `content-of-${bs[0]?.id ?? ''}`;

describe('executeSave — delete removed blocks', () => {
  let registry: ServerRegistry;

  beforeEach(() => {
    vi.clearAllMocks();
    registry = new ServerRegistry();
    mockDelete.mockResolvedValue(undefined);
  });

  it('deletes server node when block is removed from document', async () => {
    const block = makeBlock('b1');
    registry.set('b1', { nodeId: 'n1', version: 1, nodeType: 'markdown' });
    const snapshot = new Map([['b1', 'old content']]);
    const editor = makeEditor([], serialize); // b1 no longer in document

    await executeSave('nb', 'note', editor, registry, snapshot);

    expect(mockDelete).toHaveBeenCalledWith('nb', 'note', 'n1');
  });

  it('does not delete when block remains in document', async () => {
    const block = makeBlock('b1');
    registry.set('b1', { nodeId: 'n1', version: 1, nodeType: 'markdown' });
    const snapshot = new Map([['b1', serialize([block])]]);
    const editor = makeEditor([block], serialize);

    await executeSave('nb', 'note', editor, registry, snapshot);

    expect(mockDelete).not.toHaveBeenCalled();
  });
});

describe('executeSave — create new blocks', () => {
  let registry: ServerRegistry;

  beforeEach(() => {
    vi.clearAllMocks();
    registry = new ServerRegistry();
    mockCreate.mockResolvedValue(makeNode('node-new', 2));
  });

  it('creates a server node for a block with no registry entry', async () => {
    const block = makeBlock('b-new', 'paragraph');
    const editor = makeEditor([block], serialize);

    await executeSave('nb', 'note', editor, registry, new Map());

    expect(mockCreate).toHaveBeenCalledWith('nb', 'note', serialize([block]), expect.objectContaining({
      blockType: 'paragraph',
    }));
  });

  it('registers the new block after creation', async () => {
    const block = makeBlock('b-new');
    const editor = makeEditor([block], serialize);
    mockCreate.mockResolvedValue({ ...makeNode('node-created', 1) });

    await executeSave('nb', 'note', editor, registry, new Map());

    expect(registry.get('b-new')).toMatchObject({ nodeId: 'node-created' });
  });

  it('provides afterNodeId from the preceding registered block', async () => {
    const b1 = makeBlock('b1');
    const b2 = makeBlock('b2');
    registry.set('b1', { nodeId: 'n1', version: 1, nodeType: 'markdown' });
    const snapshot = new Map([['b1', serialize([b1])]]);
    const editor = makeEditor([b1, b2], serialize);

    await executeSave('nb', 'note', editor, registry, snapshot);

    expect(mockCreate).toHaveBeenCalledWith('nb', 'note', expect.any(String), expect.objectContaining({
      afterNodeId: 'n1',
    }));
  });

  it('provides beforeNodeId from the following registered block', async () => {
    const b1 = makeBlock('b1');
    const b2 = makeBlock('b2');
    registry.set('b2', { nodeId: 'n2', version: 1, nodeType: 'markdown' });
    const snapshot = new Map([['b2', serialize([b2])]]);
    const editor = makeEditor([b1, b2], serialize);

    await executeSave('nb', 'note', editor, registry, snapshot);

    expect(mockCreate).toHaveBeenCalledWith('nb', 'note', expect.any(String), expect.objectContaining({
      beforeNodeId: 'n2',
    }));
  });
});

describe('executeSave — update changed blocks', () => {
  let registry: ServerRegistry;

  beforeEach(() => {
    vi.clearAllMocks();
    registry = new ServerRegistry();
    mockUpdate.mockResolvedValue(makeNode('n1', 2));
  });

  it('patches a block when content has changed', async () => {
    const block = makeBlock('b1');
    registry.set('b1', { nodeId: 'n1', version: 1, nodeType: 'markdown' });
    const snapshot = new Map([['b1', 'old content']]);
    const editor = makeEditor([block], () => 'new content');

    await executeSave('nb', 'note', editor, registry, snapshot);

    expect(mockUpdate).toHaveBeenCalledWith('nb', 'note', 'n1', 'new content', 1, 'paragraph');
  });

  it('does not patch when content is unchanged', async () => {
    const block = makeBlock('b1');
    registry.set('b1', { nodeId: 'n1', version: 1, nodeType: 'markdown' });
    const editor = makeEditor([block], () => 'same content');
    const snapshot = new Map([['b1', 'same content']]);

    await executeSave('nb', 'note', editor, registry, snapshot);

    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it('updates the registry version after a successful patch', async () => {
    const block = makeBlock('b1');
    registry.set('b1', { nodeId: 'n1', version: 1, nodeType: 'markdown' });
    mockUpdate.mockResolvedValue({ ...makeNode('n1', 7) });
    const editor = makeEditor([block], () => 'changed');
    const snapshot = new Map([['b1', 'original']]);

    await executeSave('nb', 'note', editor, registry, snapshot);

    expect(registry.get('b1')?.version).toBe(7);
  });
});

describe('executeSave — block type mapping', () => {
  let registry: ServerRegistry;

  beforeEach(() => {
    vi.clearAllMocks();
    registry = new ServerRegistry();
    mockCreate.mockResolvedValue(makeNode('n-new', 1));
  });

  const cases: [string, string][] = [
    ['paragraph', 'paragraph'],
    ['heading', 'heading'],
    ['bulletListItem', 'list_item'],
    ['numberedListItem', 'list_item'],
    ['checkListItem', 'list_item'],
    ['codeBlock', 'code_block'],
    ['quote', 'blockquote'],
    ['image', 'image'],
    ['unknownType', 'paragraph'],
  ];

  it.each(cases)('maps %s → %s', async (blockNoteType, serverType) => {
    const block = makeBlock('b1', blockNoteType);
    const editor = makeEditor([block], () => 'text');
    await executeSave('nb', 'note', editor, registry, new Map());
    expect(mockCreate).toHaveBeenCalledWith('nb', 'note', expect.any(String), expect.objectContaining({
      blockType: serverType,
    }));
  });
});

describe('executeSave — legacy TEXT node migration', () => {
  let registry: ServerRegistry;

  beforeEach(() => {
    vi.clearAllMocks();
    registry = new ServerRegistry();
    mockDelete.mockResolvedValue(undefined);
    mockCreate.mockResolvedValue(makeNode('n-new', 1));
  });

  it('deletes the old TEXT node and recreates as markdown', async () => {
    const block = makeBlock('b1');
    registry.set('b1', { nodeId: 'n-text', version: 1, nodeType: 'text' });
    const snapshot = new Map([['b1', 'original']]);
    const editor = makeEditor([block], () => 'text');

    await executeSave('nb', 'note', editor, registry, snapshot);

    expect(mockDelete).toHaveBeenCalledWith('nb', 'note', 'n-text');
    expect(mockCreate).toHaveBeenCalledWith('nb', 'note', expect.any(String), expect.anything());
  });
});

describe('executeSave — returned snapshot', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockCreate.mockResolvedValue(makeNode('n-new', 1));
    mockUpdate.mockResolvedValue(makeNode('n1', 2));
    mockDelete.mockResolvedValue(undefined);
  });

  it('returns a snapshot of the current document after save', async () => {
    const registry = new ServerRegistry();
    const block = makeBlock('b1');
    registry.set('b1', { nodeId: 'n1', version: 1, nodeType: 'markdown' });
    const snapshot = new Map([['b1', 'old']]);
    const editor = makeEditor([block], () => 'new content');

    const newSnapshot = await executeSave('nb', 'note', editor, registry, snapshot);

    expect(newSnapshot.get('b1')).toBe('new content');
  });
});
