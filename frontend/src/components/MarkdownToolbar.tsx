import type { BlockNoteEditor } from '@blocknote/core';
import type { MouseEvent as ReactMouseEvent } from 'react';

interface MarkdownToolbarProps {
  editor: BlockNoteEditor;
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

export default function MarkdownToolbar({ editor }: MarkdownToolbarProps) {
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
    </div>
  );
}
