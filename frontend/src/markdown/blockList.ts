/**
 * Doubly-linked list of markdown blocks that serves as the in-memory document
 * model for the editor. Each node tracks its server-side state so the
 * reconciler can diff local edits into API calls on save.
 */

import type { MarkdownBlockType, NoteNode } from '../types';
import { classifyBlockType, parseMarkdownBlocks } from './parser';

export interface BlockNode {
  prev: BlockNode | null;
  next: BlockNode | null;
  blockType: MarkdownBlockType;
  content: string;
  lineCount: number;
  lineStart: number;
  serverState: { nodeId: string; version: number; nodeType: string } | null;
  dirty: boolean;
}

function countLines(content: string): number {
  if (content === '') return 1;
  return content.split('\n').length;
}

export class BlockList {
  head: BlockNode | null = null;
  tail: BlockNode | null = null;
  deletedNodeIds: string[] = [];

  buildFromServerNodes(nodes: NoteNode[]): void {
    this.head = null;
    this.tail = null;
    this.deletedNodeIds = [];

    for (const node of nodes) {
      const content = node.payload ?? '';

      if (node.node_type === 'markdown') {
        const block: BlockNode = {
          prev: null,
          next: null,
          blockType: (node.block_type as MarkdownBlockType) ?? classifyBlockType(content),
          content,
          lineCount: countLines(content),
          lineStart: 0,
          serverState: { nodeId: node.id, version: node.version, nodeType: 'markdown' },
          dirty: false,
        };
        this.appendBlock(block);
      } else {
        // TEXT nodes: parse content into blocks so multi-block text gets split
        const parsed = parseMarkdownBlocks(content);
        for (let i = 0; i < parsed.length; i++) {
          const block: BlockNode = {
            prev: null,
            next: null,
            blockType: parsed[i].blockType,
            content: parsed[i].content,
            lineCount: parsed[i].lineCount,
            lineStart: 0,
            serverState: i === 0
              ? { nodeId: node.id, version: node.version, nodeType: 'text' }
              : null,
            dirty: i > 0,
          };
          this.appendBlock(block);
        }
      }
    }

    this.recomputeLineStarts();
  }

  buildFromText(text: string): void {
    this.head = null;
    this.tail = null;
    this.deletedNodeIds = [];

    const parsed = parseMarkdownBlocks(text);
    for (const p of parsed) {
      const block: BlockNode = {
        prev: null,
        next: null,
        blockType: p.blockType,
        content: p.content,
        lineCount: p.lineCount,
        lineStart: 0,
        serverState: null,
        dirty: true,
      };
      this.appendBlock(block);
    }

    this.recomputeLineStarts();
  }

  private appendBlock(block: BlockNode): void {
    if (this.tail === null) {
      this.head = block;
      this.tail = block;
    } else {
      block.prev = this.tail;
      this.tail.next = block;
      this.tail = block;
    }
  }

  getBlockAtLine(line: number): BlockNode | null {
    let current = this.head;
    while (current !== null) {
      if (line >= current.lineStart && line < current.lineStart + current.lineCount) {
        return current;
      }
      current = current.next;
    }
    return this.tail;
  }

  insertAfter(after: BlockNode | null, blockType: MarkdownBlockType, content: string): BlockNode {
    const block: BlockNode = {
      prev: null,
      next: null,
      blockType,
      content,
      lineCount: countLines(content),
      lineStart: 0,
      serverState: null,
      dirty: true,
    };

    if (after === null) {
      // Insert at head
      block.next = this.head;
      if (this.head) this.head.prev = block;
      this.head = block;
      if (this.tail === null) this.tail = block;
    } else {
      block.prev = after;
      block.next = after.next;
      if (after.next) after.next.prev = block;
      after.next = block;
      if (after === this.tail) this.tail = block;
    }

    this.recomputeLineStarts();
    return block;
  }

  remove(block: BlockNode): void {
    if (block.serverState) {
      this.deletedNodeIds.push(block.serverState.nodeId);
    }

    if (block.prev) {
      block.prev.next = block.next;
    } else {
      this.head = block.next;
    }

    if (block.next) {
      block.next.prev = block.prev;
    } else {
      this.tail = block.prev;
    }

    block.prev = null;
    block.next = null;
    this.recomputeLineStarts();
  }

  updateBlock(block: BlockNode, newContent: string): void {
    block.content = newContent;
    block.lineCount = countLines(newContent);
    block.blockType = classifyBlockType(newContent);
    block.dirty = true;
    this.recomputeLineStarts();
  }

  splitBlock(block: BlockNode, localLineOffset: number): BlockNode {
    const lines = block.content.split('\n');
    const topContent = lines.slice(0, localLineOffset).join('\n');
    const bottomContent = lines.slice(localLineOffset).join('\n');

    block.content = topContent;
    block.lineCount = countLines(topContent);
    block.blockType = classifyBlockType(topContent);
    block.dirty = true;

    const newBlock = this.insertAfter(block, classifyBlockType(bottomContent), bottomContent);
    return newBlock;
  }

  mergeWithNext(block: BlockNode): void {
    const next = block.next;
    if (!next) return;

    block.content = block.content + '\n' + next.content;
    block.lineCount = countLines(block.content);
    block.blockType = classifyBlockType(block.content);
    block.dirty = true;

    this.remove(next);
  }

  toText(): string {
    const parts: string[] = [];
    let current = this.head;
    while (current !== null) {
      parts.push(current.content);
      current = current.next;
    }
    return parts.join('\n\n');
  }

  recomputeLineStarts(): void {
    let lineStart = 0;
    let current = this.head;
    let isFirst = true;
    while (current !== null) {
      if (!isFirst) {
        lineStart += 1; // blank separator line between blocks
      }
      current.lineStart = lineStart;
      lineStart += current.lineCount;
      current = current.next;
      isFirst = false;
    }
  }

  toArray(): BlockNode[] {
    const result: BlockNode[] = [];
    let current = this.head;
    while (current !== null) {
      result.push(current);
      current = current.next;
    }
    return result;
  }

  totalLines(): number {
    const blocks = this.toArray();
    if (blocks.length === 0) return 0;
    const last = blocks[blocks.length - 1];
    return last.lineStart + last.lineCount;
  }
}
