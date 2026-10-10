/** One-field input dialog in a text frame (new notebook / note, filter). Esc cancels. */

import { useState } from 'react';
import TuiBorder from './TuiBorder';

export default function TuiPrompt({
  title,
  label,
  initialValue = '',
  allowEmpty = false,
  onSubmit,
  onCancel,
}: {
  title: string;
  label: string;
  initialValue?: string;
  /** Accept an empty value (e.g. to clear a filter). */
  allowEmpty?: boolean;
  onSubmit: (value: string) => void;
  onCancel: () => void;
}) {
  const [value, setValue] = useState(initialValue);
  const trimmed = value.trim();

  return (
    <div className="modal-overlay" onClick={onCancel}>
      <div
        className="modal tui-dialog tui-framed"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <TuiBorder title={title} active />
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (trimmed || allowEmpty) onSubmit(trimmed);
          }}
        >
          <label className="tui-field">
            <span>{label}</span>
            <input
              autoFocus
              value={value}
              onChange={(e) => setValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  e.preventDefault();
                  onCancel();
                }
              }}
            />
          </label>
          <div className="tui-dialog-actions">
            <button type="submit" disabled={!trimmed && !allowEmpty}>OK</button>
            <button type="button" onClick={onCancel}>Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}
