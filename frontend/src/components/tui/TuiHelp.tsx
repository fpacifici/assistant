/** F1 help: the TUI key map. Any key or click closes it. */

import { useEffect } from 'react';
import TuiBorder from './TuiBorder';
import { FKEY_LABELS } from './keys';

const NAVIGATION: [string, string][] = [
  ['↑ ↓  PgUp PgDn  Home End', 'Move the cursor'],
  ['Enter', 'Open notebook / note'],
  ['Tab  Shift+Tab', 'Next / previous pane'],
  ['← →', 'Pane to the left / right'],
  ['Esc', 'Leave the editor or a field'],
  ['Alt+1 … Alt+0', 'Same as F1 … F10'],
  ['Esc, then 1 … 0', 'Same as F1 … F10'],
];

const FKEY_HELP: Record<number, string> = {
  1: 'This help',
  2: 'Share the notebook / note',
  3: 'Hide or show the notebooks pane',
  4: 'Edit the note',
  5: 'Add tags to the note',
  6: 'Filter the list',
  7: 'New notebook / note',
  8: 'Delete the notebook / note',
  9: 'Menu bar',
  10: 'Back to the classic layout',
};

export default function TuiHelp({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      e.preventDefault();
      onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal tui-dialog tui-help tui-framed" role="dialog" aria-label="Keys">
        <TuiBorder title="Keys" footer="any key to close" active />
        <table>
          <tbody>
            {Object.entries(FKEY_HELP).map(([n, text]) => (
              <tr key={n}>
                <th>F{n}</th>
                <td>{FKEY_LABELS[Number(n)]}</td>
                <td>{text}</td>
              </tr>
            ))}
            {NAVIGATION.map(([keys, text]) => (
              <tr key={keys}>
                <th colSpan={2}>{keys}</th>
                <td>{text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
