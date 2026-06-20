import { describe, it, expect } from 'vitest';
import { classifyBlockType, parseMarkdownBlocks } from './parser';

describe('classifyBlockType', () => {
  it('identifies headings', () => {
    expect(classifyBlockType('# Title')).toBe('heading');
    expect(classifyBlockType('## Subtitle')).toBe('heading');
    expect(classifyBlockType('###### Deep heading')).toBe('heading');
  });

  it('requires a space after hash marks', () => {
    expect(classifyBlockType('#NoSpace')).toBe('paragraph');
  });

  it('identifies blockquotes', () => {
    expect(classifyBlockType('> quoted text')).toBe('blockquote');
    expect(classifyBlockType('>compact quote')).toBe('blockquote');
  });

  it('identifies unordered list items', () => {
    expect(classifyBlockType('- item')).toBe('list_item');
    expect(classifyBlockType('* item')).toBe('list_item');
    expect(classifyBlockType('+ item')).toBe('list_item');
  });

  it('identifies ordered list items', () => {
    expect(classifyBlockType('1. first')).toBe('list_item');
    expect(classifyBlockType('42. forty-second')).toBe('list_item');
  });

  it('identifies images', () => {
    expect(classifyBlockType('![alt](url.png)')).toBe('image');
  });

  it('identifies code blocks', () => {
    expect(classifyBlockType('```js\nconsole.log("hi")\n```')).toBe('code_block');
    expect(classifyBlockType('```')).toBe('code_block');
  });

  it('defaults to paragraph', () => {
    expect(classifyBlockType('just some text')).toBe('paragraph');
    expect(classifyBlockType('')).toBe('paragraph');
  });

  it('classifies based on first line only', () => {
    expect(classifyBlockType('# heading\nsome paragraph text')).toBe('heading');
  });

  it('handles leading whitespace on the first line', () => {
    expect(classifyBlockType('  # heading')).toBe('heading');
    expect(classifyBlockType('  > quote')).toBe('blockquote');
  });
});

describe('parseMarkdownBlocks', () => {
  it('returns a single empty paragraph for empty string', () => {
    const blocks = parseMarkdownBlocks('');
    expect(blocks).toEqual([
      { blockType: 'paragraph', content: '', lineCount: 1 },
    ]);
  });

  it('parses a single paragraph', () => {
    const blocks = parseMarkdownBlocks('hello world');
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toEqual({
      blockType: 'paragraph',
      content: 'hello world',
      lineCount: 1,
    });
  });

  it('parses multiple paragraphs separated by blank lines', () => {
    const blocks = parseMarkdownBlocks('first paragraph\n\nsecond paragraph');
    expect(blocks).toHaveLength(2);
    expect(blocks[0].content).toBe('first paragraph');
    expect(blocks[1].content).toBe('second paragraph');
  });

  it('parses a heading block', () => {
    const blocks = parseMarkdownBlocks('# My Title');
    expect(blocks).toHaveLength(1);
    expect(blocks[0].blockType).toBe('heading');
  });

  it('parses mixed block types', () => {
    const text = '# Title\n\nSome paragraph\n\n> A quote\n\n- item 1\n- item 2';
    const blocks = parseMarkdownBlocks(text);
    expect(blocks).toHaveLength(4);
    expect(blocks[0].blockType).toBe('heading');
    expect(blocks[1].blockType).toBe('paragraph');
    expect(blocks[2].blockType).toBe('blockquote');
    expect(blocks[3].blockType).toBe('list_item');
  });

  it('treats consecutive non-blank lines as one block', () => {
    const text = 'line one\nline two\nline three';
    const blocks = parseMarkdownBlocks(text);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].content).toBe('line one\nline two\nline three');
    expect(blocks[0].lineCount).toBe(3);
  });

  it('parses a fenced code block', () => {
    const text = '```js\nconst x = 1;\nconsole.log(x);\n```';
    const blocks = parseMarkdownBlocks(text);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].blockType).toBe('code_block');
    expect(blocks[0].lineCount).toBe(4);
  });

  it('parses code block with surrounding text', () => {
    const text = 'before\n\n```\ncode\n```\n\nafter';
    const blocks = parseMarkdownBlocks(text);
    expect(blocks).toHaveLength(3);
    expect(blocks[0].blockType).toBe('paragraph');
    expect(blocks[1].blockType).toBe('code_block');
    expect(blocks[2].blockType).toBe('paragraph');
  });

  it('handles unclosed code block', () => {
    const text = '```\ncode without closing';
    const blocks = parseMarkdownBlocks(text);
    expect(blocks).toHaveLength(1);
    expect(blocks[0].blockType).toBe('code_block');
    expect(blocks[0].content).toBe('```\ncode without closing');
  });

  it('handles multiple blank lines between blocks', () => {
    const text = 'first\n\n\n\nsecond';
    const blocks = parseMarkdownBlocks(text);
    expect(blocks).toHaveLength(2);
    expect(blocks[0].content).toBe('first');
    expect(blocks[1].content).toBe('second');
  });

  it('handles only blank lines', () => {
    const text = '\n\n\n';
    const blocks = parseMarkdownBlocks(text);
    expect(blocks).toHaveLength(1);
    expect(blocks[0]).toEqual({ blockType: 'paragraph', content: '', lineCount: 1 });
  });
});
