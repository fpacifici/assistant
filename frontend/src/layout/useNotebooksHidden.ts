/**
 * Desktop preference: hide the notebooks column while a notebook is open.
 * Remembered per browser in `localStorage` (`assistant.notebooksHidden`).
 */

import { useCallback, useState } from 'react';

export const NOTEBOOKS_HIDDEN_KEY = 'assistant.notebooksHidden';

function readHidden(): boolean {
  try {
    return localStorage.getItem(NOTEBOOKS_HIDDEN_KEY) === 'true';
  } catch {
    return false;
  }
}

function writeHidden(hidden: boolean): void {
  try {
    if (hidden) localStorage.setItem(NOTEBOOKS_HIDDEN_KEY, 'true');
    else localStorage.removeItem(NOTEBOOKS_HIDDEN_KEY);
  } catch {
    // Storage unavailable (private mode, blocked): the choice lasts this page only.
  }
}

export function useNotebooksHidden(): [boolean, () => void] {
  const [hidden, setHidden] = useState(readHidden);
  const toggle = useCallback(() => {
    setHidden((prev) => {
      writeHidden(!prev);
      return !prev;
    });
  }, []);
  return [hidden, toggle];
}
