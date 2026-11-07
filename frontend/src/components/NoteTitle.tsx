/**
 * The note's title, shown at the top of the note as an H2, as if it were the
 * first line of the text, and edited in place.
 *
 * It is not a block of the document: it is the note's `title`, saved with
 * `PATCH` by the caller's autosave. A newline can't go in a title, so Enter
 * (or a pasted line break) ends it, and Enter moves on to the text.
 */

import { useLayoutEffect, useRef } from 'react';

/** As long as the server allows (`MAX_NOTE_TITLE_LENGTH`). */
export const MAX_TITLE_LENGTH = 500;

interface NoteTitleProps {
  value: string;
  readOnly: boolean;
  onChange: (title: string) => void;
  /** Enter: save now and continue in the text. */
  onCommit: () => void;
  /** Escape: drop the unsaved title. */
  onCancel: () => void;
  /** Leaving the field saves it. */
  onBlur: () => void;
}

export default function NoteTitle({
  value,
  readOnly,
  onChange,
  onCommit,
  onCancel,
  onBlur,
}: NoteTitleProps) {
  const ref = useRef<HTMLTextAreaElement>(null);

  // A textarea, so long titles wrap like a heading; it grows to fit.
  useLayoutEffect(() => {
    const field = ref.current;
    if (!field) return;
    field.style.height = 'auto';
    field.style.height = `${field.scrollHeight}px`;
  }, [value]);

  return (
    <h2 className="note-title">
      <textarea
        ref={ref}
        aria-label="Note title"
        placeholder="Untitled"
        rows={1}
        maxLength={MAX_TITLE_LENGTH}
        value={value}
        readOnly={readOnly}
        spellCheck
        onChange={(e) => onChange(e.target.value.replace(/[\r\n]+/g, ' '))}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
            e.preventDefault();
            onCommit();
          } else if (e.key === 'Escape') {
            e.preventDefault();
            onCancel();
            e.currentTarget.blur();
          }
        }}
        onBlur={onBlur}
      />
    </h2>
  );
}
