import { useRef, useState } from 'react';
import type { BlockNoteEditor } from '@blocknote/core';
import type { MouseEvent as ReactMouseEvent } from 'react';
import { createFile, uploadChunk, completeFile } from '../api/files';
import { createNode } from '../api/nodes';
import type { NoteNode } from '../types';

interface MarkdownToolbarProps {
  editor: BlockNoteEditor;
  notebookId: string;
  noteId: string;
  onAttached: (node: NoteNode) => void;
}

const BLOCK_BUTTONS = [
  { label: 'P', title: 'Paragraph', type: 'paragraph', props: {} },
  { label: 'H1', title: 'Heading 1', type: 'heading', props: { level: 1 } },
  { label: 'H2', title: 'Heading 2', type: 'heading', props: { level: 2 } },
  { label: 'H3', title: 'Heading 3', type: 'heading', props: { level: 3 } },
  { label: '•', title: 'Bullet list', type: 'bulletListItem', props: {} },
  { label: '1.', title: 'Numbered list', type: 'numberedListItem', props: {} },
  { label: '" "', title: 'Quote', type: 'quote', props: {} },
  { label: '< >', title: 'Code block', type: 'codeBlock', props: {} },
] as const;

const STYLE_BUTTONS = [
  { label: 'B', title: 'Bold', style: 'bold', className: 'font-bold' },
  { label: 'I', title: 'Italic', style: 'italic', className: 'font-italic' },
  { label: 'U', title: 'Underline', style: 'underline', className: 'font-underline' },
  { label: 'S', title: 'Strikethrough', style: 'strike', className: 'font-strike' },
  { label: '`', title: 'Inline code', style: 'code', className: 'font-code' },
] as const;

const CHUNK_SIZE = 1024 * 1024; // 1 MB chunks

export default function MarkdownToolbar({
  editor,
  notebookId,
  noteId,
  onAttached,
}: MarkdownToolbarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);

  const applyBlockType = (
    e: ReactMouseEvent,
    type: string,
    props: Record<string, unknown>,
  ) => {
    e.preventDefault();
    try {
      const position = editor.getTextCursorPosition();
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      editor.updateBlock(position.block, { type: type as any, props: props as any });
    } catch {
      // no-op: editor may not have an active cursor position
    }
  };

  const applyStyle = (e: ReactMouseEvent, style: string) => {
    e.preventDefault();
    try {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      editor.toggleStyles({ [style]: true } as any);
    } catch {
      // no-op
    }
  };

  const handleAttachClick = (e: ReactMouseEvent) => {
    e.preventDefault();
    setUploadError(null);
    fileInputRef.current?.click();
  };

  const handleFileSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setUploadError(null);

    try {
      const fileRecord = await createFile(noteId, file.name);

      const buffer = await file.arrayBuffer();
      const totalChunks = Math.ceil(buffer.byteLength / CHUNK_SIZE) || 1;
      for (let i = 0; i < totalChunks; i++) {
        const chunk = buffer.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE);
        await uploadChunk(fileRecord.id, i + 1, chunk);
      }

      await completeFile(fileRecord.id);

      const node = await createNode(notebookId, noteId, { file_id: fileRecord.id });

      onAttached(node);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  return (
    <div className="markdown-toolbar">
      <div className="toolbar-group">
        {BLOCK_BUTTONS.map((btn) => (
          <button
            key={btn.label}
            title={btn.title}
            className="toolbar-btn"
            onMouseDown={(e) => applyBlockType(e, btn.type, btn.props)}
          >
            {btn.label}
          </button>
        ))}
      </div>
      <div className="toolbar-divider" />
      <div className="toolbar-group">
        {STYLE_BUTTONS.map((btn) => (
          <button
            key={btn.label}
            title={btn.title}
            className={`toolbar-btn ${btn.className}`}
            onMouseDown={(e) => applyStyle(e, btn.style)}
          >
            {btn.label}
          </button>
        ))}
      </div>
      <div className="toolbar-divider" />
      <div className="toolbar-group">
        <button
          title="Attach file"
          className="toolbar-btn"
          onMouseDown={handleAttachClick}
          disabled={uploading}
        >
          {uploading ? '…' : '📎'}
        </button>
        {uploadError && (
          <span className="status error" title={uploadError}>
            Upload failed
          </span>
        )}
      </div>
      <input
        ref={fileInputRef}
        type="file"
        style={{ display: 'none' }}
        onChange={handleFileSelected}
      />
    </div>
  );
}
