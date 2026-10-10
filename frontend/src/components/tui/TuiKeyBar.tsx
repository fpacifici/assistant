/** Bottom function-key bar (mc style). Each key is also clickable. */

import { FKEY_LABELS } from './keys';
import { useTui } from './TuiContext';

const FKEYS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];

export default function TuiKeyBar() {
  const { runFkey, notebooksHidden } = useTui();
  return (
    <nav className="tui-keybar" aria-label="Function keys">
      {FKEYS.map((n) => {
        const label = n === 3 && notebooksHidden ? 'Show' : FKEY_LABELS[n];
        return (
          <button
            key={n}
            type="button"
            className="tui-key"
            title={`F${n} (Alt+${n % 10}, or Esc then ${n % 10})`}
            aria-label={`F${n} ${label}`}
            // Keep focus in the active pane.
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => runFkey(n)}
          >
            <span className="tui-key-num">{n}</span>
            <span className="tui-key-label">{label}</span>
          </button>
        );
      })}
    </nav>
  );
}
