/** Theme pickers: a select for the desktop header, radio items for the mobile `⋯` menu. */

import { useTheme } from '../theme/ThemeContext';
import { THEME_LABELS as LABELS, THEME_PREFERENCES } from '../theme/theme';
import type { ThemePreference } from '../theme/theme';

export function ThemeSelect() {
  const { preference, setPreference } = useTheme();
  return (
    <select
      className="theme-select"
      aria-label="Theme"
      value={preference}
      onChange={(e) => setPreference(e.target.value as ThemePreference)}
    >
      {THEME_PREFERENCES.map((p) => (
        <option key={p} value={p}>{LABELS[p]}</option>
      ))}
    </select>
  );
}

/** `menuitemradio` entries; they keep the menu open so the change is visible. */
export function ThemeMenuItems() {
  const { preference, setPreference } = useTheme();
  return (
    <div className="overflow-menu-group" role="group" aria-label="Theme">
      <span className="overflow-menu-group-label" aria-hidden="true">Theme</span>
      {THEME_PREFERENCES.map((p) => (
        <button
          key={p}
          role="menuitemradio"
          aria-checked={preference === p}
          onClick={() => setPreference(p)}
        >
          {LABELS[p]}
        </button>
      ))}
    </div>
  );
}
