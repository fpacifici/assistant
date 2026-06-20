import { describe, it, expect } from 'vitest';
import { BlockList } from './blockList';
import type { NoteNode } from '../types';

function makeNode(overrides: Partial<NoteNode> = {}): NoteNode {
  return {
    id: 'node-1',
    note_id: 'note-1',
    author_id: 'user-1',
    node_type: 'markdown',
    payload: 'hello',
    block_type: 'paragraph',
    version: 1,
    update_timestamp: '2024-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('BlockList', () => {
  describe('buildFromText', () => {
    it('builds blocks from simple text', () => {
      const bl = new BlockList();
      bl.buildFromText('hello world');
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(1);
      expect(blocks[0].content).toBe('hello world');
      expect(blocks[0].blockType).toBe('paragraph');
      expect(blocks[0].dirty).toBe(true);
      expect(blocks[0].serverState).toBeNull();
    });

    it('builds multiple blocks separated by blank lines', () => {
      const bl = new BlockList();
      bl.buildFromText('# Title\n\nParagraph text');
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(2);
      expect(blocks[0].blockType).toBe('heading');
      expect(blocks[1].blockType).toBe('paragraph');
    });

    it('sets correct line starts', () => {
      const bl = new BlockList();
      bl.buildFromText('line1\n\nline2\nline3');
      const blocks = bl.toArray();
      expect(blocks[0].lineStart).toBe(0);
      expect(blocks[0].lineCount).toBe(1);
      expect(blocks[1].lineStart).toBe(2); // +1 for separator line
      expect(blocks[1].lineCount).toBe(2);
    });

    it('resets state on rebuild', () => {
      const bl = new BlockList();
      bl.buildFromText('first');
      bl.deletedNodeIds.push('old-id');
      bl.buildFromText('second');
      expect(bl.toArray()).toHaveLength(1);
      expect(bl.toArray()[0].content).toBe('second');
      expect(bl.deletedNodeIds).toEqual([]);
    });
  });

  describe('buildFromServerNodes', () => {
    it('builds from markdown nodes', () => {
      const bl = new BlockList();
      bl.buildFromServerNodes([
        makeNode({ id: 'n1', payload: '# Title', block_type: 'heading' }),
        makeNode({ id: 'n2', payload: 'Body text', block_type: 'paragraph' }),
      ]);
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(2);
      expect(blocks[0].serverState).toEqual({ nodeId: 'n1', version: 1, nodeType: 'markdown' });
      expect(blocks[0].dirty).toBe(false);
      expect(blocks[1].serverState).toEqual({ nodeId: 'n2', version: 1, nodeType: 'markdown' });
    });

    it('splits text nodes into multiple blocks', () => {
      const bl = new BlockList();
      bl.buildFromServerNodes([
        makeNode({ id: 'n1', node_type: 'text', payload: '# Title\n\nBody text', block_type: null }),
      ]);
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(2);
      expect(blocks[0].serverState).toEqual({ nodeId: 'n1', version: 1, nodeType: 'text' });
      expect(blocks[0].dirty).toBe(false);
      expect(blocks[1].serverState).toBeNull();
      expect(blocks[1].dirty).toBe(true);
    });

    it('handles null payload as empty string', () => {
      const bl = new BlockList();
      bl.buildFromServerNodes([makeNode({ payload: null })]);
      const blocks = bl.toArray();
      expect(blocks[0].content).toBe('');
    });
  });

  describe('toText', () => {
    it('joins blocks with double newlines', () => {
      const bl = new BlockList();
      bl.buildFromText('first\n\nsecond\n\nthird');
      expect(bl.toText()).toBe('first\n\nsecond\n\nthird');
    });

    it('returns empty for single empty block', () => {
      const bl = new BlockList();
      bl.buildFromText('');
      expect(bl.toText()).toBe('');
    });
  });

  describe('getBlockAtLine', () => {
    it('returns block containing the given line', () => {
      const bl = new BlockList();
      bl.buildFromText('line0\n\nline2\nline3');
      // block0: lineStart=0, lineCount=1 (line 0)
      // block1: lineStart=2, lineCount=2 (lines 2, 3)
      expect(bl.getBlockAtLine(0)?.content).toBe('line0');
      expect(bl.getBlockAtLine(2)?.content).toBe('line2\nline3');
      expect(bl.getBlockAtLine(3)?.content).toBe('line2\nline3');
    });

    it('returns tail for lines beyond the last block', () => {
      const bl = new BlockList();
      bl.buildFromText('only');
      expect(bl.getBlockAtLine(100)?.content).toBe('only');
    });

    it('returns null for empty list', () => {
      const bl = new BlockList();
      expect(bl.getBlockAtLine(0)).toBeNull();
    });
  });

  describe('insertAfter', () => {
    it('inserts at head when after is null', () => {
      const bl = new BlockList();
      bl.buildFromText('existing');
      bl.insertAfter(null, 'heading', '# New');
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(2);
      expect(blocks[0].content).toBe('# New');
      expect(blocks[1].content).toBe('existing');
    });

    it('inserts after a given block', () => {
      const bl = new BlockList();
      bl.buildFromText('first\n\nthird');
      const first = bl.head!;
      bl.insertAfter(first, 'paragraph', 'second');
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(3);
      expect(blocks[0].content).toBe('first');
      expect(blocks[1].content).toBe('second');
      expect(blocks[2].content).toBe('third');
    });

    it('inserts at the end when after is tail', () => {
      const bl = new BlockList();
      bl.buildFromText('first');
      bl.insertAfter(bl.tail!, 'paragraph', 'last');
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(2);
      expect(blocks[1].content).toBe('last');
      expect(bl.tail?.content).toBe('last');
    });

    it('marks inserted block as dirty', () => {
      const bl = new BlockList();
      bl.buildFromText('existing');
      const inserted = bl.insertAfter(bl.head, 'paragraph', 'new');
      expect(inserted.dirty).toBe(true);
      expect(inserted.serverState).toBeNull();
    });

    it('recomputes line starts after insertion', () => {
      const bl = new BlockList();
      bl.buildFromText('a\n\nb');
      bl.insertAfter(bl.head!, 'paragraph', 'middle');
      const blocks = bl.toArray();
      expect(blocks[0].lineStart).toBe(0);
      expect(blocks[1].lineStart).toBe(2);
      expect(blocks[2].lineStart).toBe(4);
    });
  });

  describe('remove', () => {
    it('removes head block', () => {
      const bl = new BlockList();
      bl.buildFromText('first\n\nsecond');
      bl.remove(bl.head!);
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(1);
      expect(blocks[0].content).toBe('second');
      expect(bl.head?.content).toBe('second');
    });

    it('removes tail block', () => {
      const bl = new BlockList();
      bl.buildFromText('first\n\nsecond');
      bl.remove(bl.tail!);
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(1);
      expect(blocks[0].content).toBe('first');
      expect(bl.tail?.content).toBe('first');
    });

    it('removes middle block', () => {
      const bl = new BlockList();
      bl.buildFromText('first\n\nsecond\n\nthird');
      const middle = bl.toArray()[1];
      bl.remove(middle);
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(2);
      expect(blocks[0].content).toBe('first');
      expect(blocks[1].content).toBe('third');
    });

    it('tracks deleted server node ids', () => {
      const bl = new BlockList();
      bl.buildFromServerNodes([
        makeNode({ id: 'n1', payload: 'first' }),
        makeNode({ id: 'n2', payload: 'second' }),
      ]);
      bl.remove(bl.head!);
      expect(bl.deletedNodeIds).toEqual(['n1']);
    });

    it('does not track deletion for blocks without server state', () => {
      const bl = new BlockList();
      bl.buildFromText('no server state');
      bl.remove(bl.head!);
      expect(bl.deletedNodeIds).toEqual([]);
    });
  });

  describe('updateBlock', () => {
    it('updates content, lineCount, blockType, and dirty flag', () => {
      const bl = new BlockList();
      bl.buildFromServerNodes([makeNode({ id: 'n1', payload: 'old', block_type: 'paragraph' })]);
      const block = bl.head!;
      expect(block.dirty).toBe(false);

      bl.updateBlock(block, '# New heading');
      expect(block.content).toBe('# New heading');
      expect(block.blockType).toBe('heading');
      expect(block.dirty).toBe(true);
      expect(block.lineCount).toBe(1);
    });

    it('handles multiline content', () => {
      const bl = new BlockList();
      bl.buildFromText('single');
      bl.updateBlock(bl.head!, 'line1\nline2\nline3');
      expect(bl.head!.lineCount).toBe(3);
    });
  });

  describe('splitBlock', () => {
    it('splits a block at the given line offset', () => {
      const bl = new BlockList();
      bl.buildFromText('line0\nline1\nline2');
      bl.splitBlock(bl.head!, 1);
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(2);
      expect(blocks[0].content).toBe('line0');
      expect(blocks[1].content).toBe('line1\nline2');
    });

    it('marks both blocks as dirty', () => {
      const bl = new BlockList();
      bl.buildFromServerNodes([makeNode({ payload: 'a\nb' })]);
      const newBlock = bl.splitBlock(bl.head!, 1);
      expect(bl.head!.dirty).toBe(true);
      expect(newBlock.dirty).toBe(true);
    });

    it('reclassifies block types after split', () => {
      const bl = new BlockList();
      bl.buildFromText('# heading\nparagraph text');
      bl.splitBlock(bl.head!, 1);
      const blocks = bl.toArray();
      expect(blocks[0].blockType).toBe('heading');
      expect(blocks[1].blockType).toBe('paragraph');
    });
  });

  describe('mergeWithNext', () => {
    it('merges two adjacent blocks', () => {
      const bl = new BlockList();
      bl.buildFromText('first\n\nsecond');
      bl.mergeWithNext(bl.head!);
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(1);
      expect(blocks[0].content).toBe('first\nsecond');
      expect(blocks[0].dirty).toBe(true);
    });

    it('does nothing if block has no next', () => {
      const bl = new BlockList();
      bl.buildFromText('only');
      bl.mergeWithNext(bl.head!);
      expect(bl.toArray()).toHaveLength(1);
      expect(bl.head!.content).toBe('only');
    });

    it('tracks deletion of merged server-backed block', () => {
      const bl = new BlockList();
      bl.buildFromServerNodes([
        makeNode({ id: 'n1', payload: 'first' }),
        makeNode({ id: 'n2', payload: 'second' }),
      ]);
      bl.mergeWithNext(bl.head!);
      expect(bl.deletedNodeIds).toEqual(['n2']);
    });
  });

  describe('totalLines', () => {
    it('returns 0 for empty list', () => {
      const bl = new BlockList();
      expect(bl.totalLines()).toBe(0);
    });

    it('returns correct count for single block', () => {
      const bl = new BlockList();
      bl.buildFromText('line1\nline2');
      expect(bl.totalLines()).toBe(2);
    });

    it('includes separator lines between blocks', () => {
      const bl = new BlockList();
      bl.buildFromText('a\n\nb');
      // block0: lineStart=0, lineCount=1
      // block1: lineStart=2, lineCount=1
      // total = 2 + 1 = 3
      expect(bl.totalLines()).toBe(3);
    });
  });

  describe('linked list integrity', () => {
    it('maintains prev/next pointers correctly', () => {
      const bl = new BlockList();
      bl.buildFromText('a\n\nb\n\nc');
      const blocks = bl.toArray();
      expect(blocks[0].prev).toBeNull();
      expect(blocks[0].next).toBe(blocks[1]);
      expect(blocks[1].prev).toBe(blocks[0]);
      expect(blocks[1].next).toBe(blocks[2]);
      expect(blocks[2].prev).toBe(blocks[1]);
      expect(blocks[2].next).toBeNull();
      expect(bl.head).toBe(blocks[0]);
      expect(bl.tail).toBe(blocks[2]);
    });

    it('maintains integrity after insert and remove', () => {
      const bl = new BlockList();
      bl.buildFromText('a\n\nc');
      bl.insertAfter(bl.head!, 'paragraph', 'b');
      bl.remove(bl.toArray()[1]); // remove 'b'
      const blocks = bl.toArray();
      expect(blocks).toHaveLength(2);
      expect(blocks[0].next).toBe(blocks[1]);
      expect(blocks[1].prev).toBe(blocks[0]);
    });
  });
});
