/**
 * Markdown block parser: splits raw text into typed blocks at structural
 * boundaries (blank lines, headings, fences, etc.) for the block-level editor.
 */

import type { MarkdownBlockType } from '../types';

export interface ParsedBlock {
  blockType: MarkdownBlockType;
  content: string;
  lineCount: number;
}

/** Determines the block type by inspecting the first line of content. */
export function classifyBlockType(content: string): MarkdownBlockType {
  const firstLine = content.split('\n')[0].trimStart();
  if (/^#{1,6}\s/.test(firstLine)) return 'heading';
  if (firstLine.startsWith('>')) return 'blockquote';
  if (/^[-*+]\s/.test(firstLine) || /^\d+\.\s/.test(firstLine)) return 'list_item';
  if (firstLine.startsWith('![')) return 'image';
  if (firstLine.startsWith('```')) return 'code_block';
  return 'paragraph';
}

function startsNewBlock(line: string): boolean {
  const trimmed = line.trimStart();
  if (/^#{1,6}\s/.test(trimmed)) return true;
  if (/^[-*+]\s/.test(trimmed) || /^\d+\.\s/.test(trimmed)) return true;
  if (trimmed.startsWith('![')) return true;
  return false;
}

/** Splits markdown text into an ordered array of blocks. Always returns at least one block. */
export function parseMarkdownBlocks(text: string): ParsedBlock[] {
  if (text === '') {
    return [{ blockType: 'paragraph', content: '', lineCount: 1 }];
  }

  const blocks: ParsedBlock[] = [];
  const lines = text.split('\n');
  let i = 0;

  while (i < lines.length) {
    if (lines[i].startsWith('```')) {
      const startLine = i;
      i++;
      while (i < lines.length && !lines[i].startsWith('```')) {
        i++;
      }
      if (i < lines.length) i++; // consume closing ```
      const content = lines.slice(startLine, i).join('\n');
      blocks.push({
        blockType: 'code_block',
        content,
        lineCount: i - startLine,
      });
      continue;
    }

    const startLine = i;
    const firstLineType = classifyBlockType(lines[i]);
    i++;
    if (firstLineType !== 'heading' && firstLineType !== 'image') {
      while (i < lines.length && lines[i] !== '' && !lines[i].startsWith('```')) {
        if (startsNewBlock(lines[i])) break;
        i++;
      }
    }

    if (i > startLine) {
      const content = lines.slice(startLine, i).join('\n');
      blocks.push({
        blockType: classifyBlockType(content),
        content,
        lineCount: i - startLine,
      });
    }

    // Skip blank lines between blocks
    while (i < lines.length && lines[i] === '') {
      i++;
    }
  }

  if (blocks.length === 0) {
    blocks.push({ blockType: 'paragraph', content: '', lineCount: 1 });
  }

  return blocks;
}
