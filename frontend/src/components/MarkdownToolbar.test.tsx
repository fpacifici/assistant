import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { fireEvent, waitFor } from '@testing-library/react';
import MarkdownToolbar from './MarkdownToolbar';
import type { BlockNoteEditor } from '@blocknote/core';
import * as filesApi from '../api/files';
import * as nodesApi from '../api/nodes';

vi.mock('../api/files');
vi.mock('../api/nodes');

function makeEditor(): BlockNoteEditor {
  return {
    getTextCursorPosition: vi.fn(() => ({ block: { id: 'b1', type: 'paragraph' } })),
    updateBlock: vi.fn(),
    toggleStyles: vi.fn(),
  } as unknown as BlockNoteEditor;
}

const DEFAULT_PROPS = {
  notebookId: 'nb-1',
  noteId: 'note-1',
  onAttached: vi.fn(),
};

describe('MarkdownToolbar', () => {
  let editor: BlockNoteEditor;

  beforeEach(() => {
    editor = makeEditor();
    vi.clearAllMocks();
  });

  it('renders block type buttons', () => {
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
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
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    expect(screen.getByTitle('Bold')).toBeInTheDocument();
    expect(screen.getByTitle('Italic')).toBeInTheDocument();
    expect(screen.getByTitle('Underline')).toBeInTheDocument();
    expect(screen.getByTitle('Strikethrough')).toBeInTheDocument();
    expect(screen.getByTitle('Inline code')).toBeInTheDocument();
  });

  it('renders attach file button', () => {
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    expect(screen.getByTitle('Attach file')).toBeInTheDocument();
  });

  // --- block type buttons ---

  it('converts block to heading 1 on H1 mousedown', () => {
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    fireEvent.mouseDown(screen.getByTitle('Heading 1'));
    expect(editor.updateBlock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ type: 'heading', props: { level: 1 } }),
    );
  });

  it('converts block to heading 2 on H2 mousedown', () => {
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    fireEvent.mouseDown(screen.getByTitle('Heading 2'));
    expect(editor.updateBlock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ type: 'heading', props: { level: 2 } }),
    );
  });

  it('converts block to bullet list on mousedown', () => {
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    fireEvent.mouseDown(screen.getByTitle('Bullet list'));
    expect(editor.updateBlock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ type: 'bulletListItem' }),
    );
  });

  it('converts block to code block on mousedown', () => {
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    fireEvent.mouseDown(screen.getByTitle('Code block'));
    expect(editor.updateBlock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ type: 'codeBlock' }),
    );
  });

  it('converts block to paragraph on P mousedown', () => {
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    fireEvent.mouseDown(screen.getByTitle('Paragraph'));
    expect(editor.updateBlock).toHaveBeenCalledWith(
      expect.anything(),
      expect.objectContaining({ type: 'paragraph' }),
    );
  });

  // --- inline style buttons ---

  it('toggles bold on Bold mousedown', () => {
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    fireEvent.mouseDown(screen.getByTitle('Bold'));
    expect(editor.toggleStyles).toHaveBeenCalledWith(expect.objectContaining({ bold: true }));
  });

  it('toggles italic on Italic mousedown', () => {
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    fireEvent.mouseDown(screen.getByTitle('Italic'));
    expect(editor.toggleStyles).toHaveBeenCalledWith(expect.objectContaining({ italic: true }));
  });

  it('toggles strike on Strikethrough mousedown', () => {
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    fireEvent.mouseDown(screen.getByTitle('Strikethrough'));
    expect(editor.toggleStyles).toHaveBeenCalledWith(expect.objectContaining({ strike: true }));
  });

  it('toggles code on Inline code mousedown', () => {
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    fireEvent.mouseDown(screen.getByTitle('Inline code'));
    expect(editor.toggleStyles).toHaveBeenCalledWith(expect.objectContaining({ code: true }));
  });

  // --- robustness ---

  it('does not throw when editor has no cursor position', () => {
    (editor.getTextCursorPosition as ReturnType<typeof vi.fn>).mockImplementation(() => {
      throw new Error('no cursor');
    });
    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    expect(() => fireEvent.mouseDown(screen.getByTitle('Heading 1'))).not.toThrow();
  });

  // --- attach flow ---

  it('runs full upload flow and calls onAttached on success', async () => {
    const fakeFile = new File([new Uint8Array([1, 2, 3])], 'test.bin', {
      type: 'application/octet-stream',
    });
    const mockRecord = {
      id: 'file-id-1',
      note_id: 'note-1',
      file_name: 'test.bin',
      state: 'complete' as const,
      creation_timestamp: new Date().toISOString(),
    };
    const onAttached = vi.fn();

    vi.mocked(filesApi.createFile).mockResolvedValue(mockRecord);
    vi.mocked(filesApi.uploadChunk).mockResolvedValue(undefined);
    vi.mocked(filesApi.completeFile).mockResolvedValue(mockRecord);
    vi.mocked(nodesApi.createNode).mockResolvedValue({
      id: 'node-1',
      note_id: 'note-1',
      author_id: 'user-1',
      node_type: 'attachment',
      payload: '[test.bin](/files/file-id-1)',
      block_type: null,
      version: 1,
      update_timestamp: new Date().toISOString(),
    });

    render(
      <MarkdownToolbar
        editor={editor}
        notebookId="nb-1"
        noteId="note-1"
        onAttached={onAttached}
      />,
    );

    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fakeFile] } });

    const expectedNode = {
      id: 'node-1',
      note_id: 'note-1',
      author_id: 'user-1',
      node_type: 'attachment',
      payload: '[test.bin](/files/file-id-1)',
      block_type: null,
      version: 1,
      update_timestamp: expect.any(String),
    };

    await waitFor(() => expect(onAttached).toHaveBeenCalledWith(expect.objectContaining(expectedNode)));

    expect(filesApi.createFile).toHaveBeenCalledWith('note-1', 'test.bin');
    expect(filesApi.uploadChunk).toHaveBeenCalledWith('file-id-1', 1, expect.any(ArrayBuffer));
    expect(filesApi.completeFile).toHaveBeenCalledWith('file-id-1');
    expect(nodesApi.createNode).toHaveBeenCalledWith('nb-1', 'note-1', {
      file_id: 'file-id-1',
    });
  });

  it('shows error message when upload fails', async () => {
    const fakeFile = new File(['data'], 'oops.txt', { type: 'text/plain' });

    vi.mocked(filesApi.createFile).mockRejectedValue(new Error('Server error'));

    render(<MarkdownToolbar editor={editor} {...DEFAULT_PROPS} />);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [fakeFile] } });

    await waitFor(() => expect(screen.getByText('Upload failed')).toBeInTheDocument());
  });
});
