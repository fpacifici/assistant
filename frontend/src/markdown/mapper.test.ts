import { describe, it, expect, beforeEach, vi } from 'vitest';
import { buildBlocksFromNodes, buildSnapshot } from './mapper';
import { ServerRegistry } from './serverRegistry';
import type { NoteNode } from '../types';
import type { Block, BlockNoteEditor } from '@blocknote/core';

// Minimal Block factory
const makeBlock = (id: string, type = 'paragraph', text = ''): Block =>
  ({
    id,
    type,
    props: {},
    content: text ? [{ type: 'text', text, styles: {} }] : [],
    children: [],
  }) as unknown as Block;

// Minimal NoteNode factory
const makeNode = (id: string, payload: string, nodeType = 'markdown'): NoteNode => ({
  id,
  note_id: 'note-1',
  author_id: 'user-1',
  node_type: nodeType,
  payload,
  block_type: 'paragraph',
  version: 1,
  update_timestamp: '2024-01-01T00:00:00Z',
});

describe('buildBlocksFromNodes', () => {
  let registry: ServerRegistry;
  let editor: BlockNoteEditor;

  beforeEach(() => {
    registry = new ServerRegistry();
    editor = {
      tryParseMarkdownToBlocks: vi.fn((text: string) => [makeBlock(`bn-${text}`, 'paragraph', text)]),
    } as unknown as BlockNoteEditor;
  });

  it('returns empty array for empty node list', () => {
    const blocks = buildBlocksFromNodes([], editor, registry);
    expect(blocks).toHaveLength(0);
  });

  it('produces one block per server node', () => {
    const nodes = [makeNode('n1', 'Hello'), makeNode('n2', 'World')];
    const blocks = buildBlocksFromNodes(nodes, editor, registry);
    expect(blocks).toHaveLength(2);
  });

  it('registers each block ID against its server nodeId', () => {
    const nodes = [makeNode('n1', 'text')];
    const blocks = buildBlocksFromNodes(nodes, editor, registry);
    expect(registry.get(blocks[0].id)).toMatchObject({ nodeId: 'n1', version: 1 });
  });

  it('stores the correct nodeType from the server node', () => {
    const nodes = [makeNode('n1', 'text', 'text')];
    const blocks = buildBlocksFromNodes(nodes, editor, registry);
    expect(registry.get(blocks[0].id)?.nodeType).toBe('text');
  });

  it('calls tryParseMarkdownToBlocks with the node payload', () => {
    buildBlocksFromNodes([makeNode('n1', '# Heading')], editor, registry);
    expect(editor.tryParseMarkdownToBlocks).toHaveBeenCalledWith('# Heading');
  });

  it('uses empty string when node payload is null', () => {
    const node = { ...makeNode('n1', ''), payload: null };
    buildBlocksFromNodes([node], editor, registry);
    expect(editor.tryParseMarkdownToBlocks).toHaveBeenCalledWith('');
  });

  it('clears the registry before repopulating', () => {
    registry.set('stale-id', { nodeId: 'old', version: 0, nodeType: 'markdown' });
    buildBlocksFromNodes([], editor, registry);
    expect(registry.has('stale-id')).toBe(false);
  });

  it('appends extra blocks when a node parses into multiple blocks', () => {
    const multiBlock = [makeBlock('b1', 'paragraph', 'line one'), makeBlock('b2', 'paragraph', 'line two')];
    (editor.tryParseMarkdownToBlocks as ReturnType<typeof vi.fn>).mockReturnValueOnce(multiBlock);
    const blocks = buildBlocksFromNodes([makeNode('n1', 'line one\nline two')], editor, registry);
    expect(blocks).toHaveLength(2);
    // Only the first block is registered against n1
    expect(registry.get('b1')).toMatchObject({ nodeId: 'n1' });
    expect(registry.has('b2')).toBe(false);
  });
});

describe('buildSnapshot', () => {
  it('maps each block ID to its serialized markdown', () => {
    const blocks = [makeBlock('b1', 'paragraph', 'hello'), makeBlock('b2', 'heading', '# World')];
    const editor = {
      blocksToMarkdownLossy: vi.fn((bs: Block[]) => bs[0].id === 'b1' ? 'hello' : '# World'),
    } as unknown as BlockNoteEditor;

    const snapshot = buildSnapshot(blocks, editor);
    expect(snapshot.get('b1')).toBe('hello');
    expect(snapshot.get('b2')).toBe('# World');
  });

  it('trims whitespace from serialized content', () => {
    const blocks = [makeBlock('b1')];
    const editor = {
      blocksToMarkdownLossy: vi.fn(() => '  text  \n'),
    } as unknown as BlockNoteEditor;

    const snapshot = buildSnapshot(blocks, editor);
    expect(snapshot.get('b1')).toBe('text');
  });

  it('returns empty map for empty block list', () => {
    const editor = { blocksToMarkdownLossy: vi.fn(() => '') } as unknown as BlockNoteEditor;
    expect(buildSnapshot([], editor).size).toBe(0);
  });
});
