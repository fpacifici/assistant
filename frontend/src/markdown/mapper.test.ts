import { describe, it, expect, beforeEach, vi } from 'vitest';
import { buildBlocksFromNodes, buildSnapshot } from './mapper';
import { ServerRegistry } from './serverRegistry';
import type { NoteNode } from '../types';
import { BlockNoteEditor as RealBlockNoteEditor } from '@blocknote/core';
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

// Contract between the HTML notes importer (src/assistant/adapters/html_parser.py)
// and the editor: each payload the importer writes must load, through the real
// BlockNote parser, as the block tree the importer intended.
describe('importer payload contract', () => {
  const editor = RealBlockNoteEditor.create();

  const load = (payload: string): Block[] =>
    buildBlocksFromNodes([makeNode('n1', payload)], editor, new ServerRegistry());

  const text = (block: Block): string =>
    (block.content as { text: string }[]).map((c) => c.text).join('');

  it('reads inline formatting as BlockNote styles', () => {
    const [block] = load('**a** *b* ~~c~~ `d` ***e***');
    const styled = (block.content as { text: string; styles: object }[]).filter(
      (c) => c.text.trim(),
    );
    expect(styled.map((c) => [c.text, c.styles])).toEqual([
      ['a', { bold: true }],
      ['b', { italic: true }],
      ['c', { strike: true }],
      ['d', { code: true }],
      ['e', { bold: true, italic: true }],
    ]);
  });

  it('reads a bold-only paragraph as a bold paragraph', () => {
    const blocks = load('**Section header**');
    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe('paragraph');
    expect(blocks[0].content).toMatchObject([{ text: 'Section header', styles: { bold: true } }]);
  });

  type Tree = [string, string, Tree[]];
  const tree = (block: Block): Tree => [block.type, text(block), block.children.map(tree)];

  it.each<[string, Tree]>([
    [
      '- a\n  - b\n    - c',
      ['bulletListItem', 'a', [['bulletListItem', 'b', [['bulletListItem', 'c', []]]]]],
    ],
    [
      '1. a\n   1. b\n   2. c',
      ['numberedListItem', 'a', [['numberedListItem', 'b', []], ['numberedListItem', 'c', []]]],
    ],
    [
      '10. a\n    - b',
      ['numberedListItem', 'a', [['bulletListItem', 'b', []]]],
    ],
    [
      '- a\n  1. x\n  2. y',
      ['bulletListItem', 'a', [['numberedListItem', 'x', []], ['numberedListItem', 'y', []]]],
    ],
    [
      '- [x] task\n  - [ ] sub\n  - note',
      ['checkListItem', 'task', [['checkListItem', 'sub', []], ['bulletListItem', 'note', []]]],
    ],
    ['- \n  - orphan', ['bulletListItem', '', [['bulletListItem', 'orphan', []]]]],
    ['2. \n   1. x', ['numberedListItem', '', [['numberedListItem', 'x', []]]]],
    [
      '- a\n  - \n    - b',
      ['bulletListItem', 'a', [['bulletListItem', '', [['bulletListItem', 'b', []]]]]],
    ],
  ])('reads nested list payload %j as one block with children', (payload, expected) => {
    const blocks = load(payload);
    expect(blocks).toHaveLength(1);
    expect(tree(blocks[0])).toEqual(expected);
    // What the editor saves for this block reloads as the same tree.
    const saved = editor.blocksToMarkdownLossy([blocks[0]]);
    expect(load(saved).map(tree)).toEqual([expected]);
  });

  it('shows the written numbers for consecutive numbered items', () => {
    const nodes = ['1. a', '2. b\n   1. b1', '3. c'].map((p, i) => makeNode(`n${i}`, p));
    const blocks = buildBlocksFromNodes(nodes, editor, new ServerRegistry());
    expect(blocks.map((b) => b.type)).toEqual(Array(3).fill('numberedListItem'));
    // BlockNote shows `start` when set, else continues from the previous item.
    // It drops `start` from an item with children, which then continues.
    const shown: number[] = [];
    blocks.forEach((b, i) => {
      const start = (b.props as { start?: number }).start;
      shown.push(start ?? (i > 0 ? shown[i - 1] + 1 : 1));
    });
    expect(shown).toEqual([1, 2, 3]);
  });

  it.each([
    ['- [x] done', true],
    ['- [ ] open', false],
  ])('reads %s as a check list item', (payload, checked) => {
    const blocks = load(payload);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe('checkListItem');
    expect(blocks[0].props).toMatchObject({ checked });
    expect(text(blocks[0])).toBe(payload.slice(6));
  });

  it.each([
    ['A\\[Ix, J\\] \\* B\\_c \\`d\\` \\~e\\~ a\\\\b', 'A[Ix, J] * B_c `d` ~e~ a\\b'],
    ['vector<\u200bint> a < b', 'vector<\u200bint> a < b'],
    ['\\# not a heading', '# not a heading'],
    ['\\- not a list', '- not a list'],
    ['1\\. not a list', '1. not a list'],
    ['\\> not a quote', '> not a quote'],
    ['\\---', '---'],
  ])('reads escaped text %s literally', (payload, expected) => {
    const blocks = load(payload);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].type).toBe('paragraph');
    expect(text(blocks[0])).toBe(expected);
  });
});
