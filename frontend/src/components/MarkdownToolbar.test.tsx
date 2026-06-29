import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { fireEvent } from '@testing-library/react';
import MarkdownToolbar from './MarkdownToolbar';
import type { BlockNoteEditor } from '@blocknote/core';

function makeEditor(): BlockNoteEditor {
  return {
    getTextCursorPosition: vi.fn(() => ({ block: { id: 'b1', type: 'paragraph' } })),
    updateBlock: vi.fn(),
    toggleStyles: vi.fn(),
  } as unknown as BlockNoteEditor;
}

describe('MarkdownToolbar', () => {
  let editor: BlockNoteEditor;

  beforeEach(() => {
    editor = makeEditor();
  });

  it('renders block type buttons', () => {
    render(<MarkdownToolbar editor={editor} />);
    expect(screen.getByTitle('Paragraph')).toBeInTheDocument();
    expect(screen.getByTitle('Heading 1')).toBeInTheDocument();
    expect(screen.getByTitle('Heading 2')).toBeInTheDocument();
    expect(screen.getByTitle('Heading 3')).toBeInTheDocument();
    expect(screen.getByTitle('Bullet list')).toBeInTheDocument();
    expect(screen.getByTitle('Numbered list')).toBeInTheDocument();
    expect(screen.getByTitle('Quote')).toBeInTheDocument();
    expect(screen.getByTitle('Code block')).toBeInTheDocument();
  });

  it('renders inline style buttons', () => {
    render(<MarkdownToolbar editor={editor} />);
    expect(screen.getByTitle('Bold')).toBeInTheDocument();
    expect(screen.getByTitle('Italic')).toBeInTheDocument();
    expect(screen.getByTitle('Underline')).toBeInTheDocument();
    expect(screen.getByTitle('Strikethrough')).toBeInTheDocument();
    expect(screen.getByTitle('Inline code')).toBeInTheDocument();
  });

  // --- block type buttons ---

  it('converts block to heading 1 on H1 mousedown', () => {
    render(<MarkdownToolbar editor={editor} />);
    fireEvent.mouseDown(screen.getByTitle('Heading 1'));
    expect(editor.updateBlock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ type: 'heading', props: { level: 1 } }),
    );
  });

  it('converts block to heading 2 on H2 mousedown', () => {
    render(<MarkdownToolbar editor={editor} />);
    fireEvent.mouseDown(screen.getByTitle('Heading 2'));
    expect(editor.updateBlock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ type: 'heading', props: { level: 2 } }),
    );
  });

  it('converts block to bullet list on mousedown', () => {
    render(<MarkdownToolbar editor={editor} />);
    fireEvent.mouseDown(screen.getByTitle('Bullet list'));
    expect(editor.updateBlock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ type: 'bulletListItem' }),
    );
  });

  it('converts block to code block on mousedown', () => {
    render(<MarkdownToolbar editor={editor} />);
    fireEvent.mouseDown(screen.getByTitle('Code block'));
    expect(editor.updateBlock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ type: 'codeBlock' }),
    );
  });

  it('converts block to paragraph on P mousedown', () => {
    render(<MarkdownToolbar editor={editor} />);
    fireEvent.mouseDown(screen.getByTitle('Paragraph'));
    expect(editor.updateBlock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ type: 'paragraph' }),
    );
  });

  // --- inline style buttons ---

  it('toggles bold on Bold mousedown', () => {
    render(<MarkdownToolbar editor={editor} />);
    fireEvent.mouseDown(screen.getByTitle('Bold'));
    expect(editor.toggleStyles).toHaveBeenCalledWith(expect.objectContaining({ bold: true }));
  });

  it('toggles italic on Italic mousedown', () => {
    render(<MarkdownToolbar editor={editor} />);
    fireEvent.mouseDown(screen.getByTitle('Italic'));
    expect(editor.toggleStyles).toHaveBeenCalledWith(expect.objectContaining({ italic: true }));
  });

  it('toggles strike on Strikethrough mousedown', () => {
    render(<MarkdownToolbar editor={editor} />);
    fireEvent.mouseDown(screen.getByTitle('Strikethrough'));
    expect(editor.toggleStyles).toHaveBeenCalledWith(expect.objectContaining({ strike: true }));
  });

  it('toggles code on Inline code mousedown', () => {
    render(<MarkdownToolbar editor={editor} />);
    fireEvent.mouseDown(screen.getByTitle('Inline code'));
    expect(editor.toggleStyles).toHaveBeenCalledWith(expect.objectContaining({ code: true }));
  });

  // --- robustness ---

  it('does not throw when editor has no cursor position', () => {
    (editor.getTextCursorPosition as ReturnType<typeof vi.fn>).mockImplementation(() => {
      throw new Error('no cursor');
    });
    render(<MarkdownToolbar editor={editor} />);
    expect(() => fireEvent.mouseDown(screen.getByTitle('Heading 1'))).not.toThrow();
  });
});
