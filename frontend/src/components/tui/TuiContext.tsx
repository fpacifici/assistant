/**
 * State and keyboard controller of the TUI layout: which pane has focus,
 * the F-key commands, and the menu / help overlays.
 *
 * `Layout` always renders `TuiProvider` (so switching layout mode never
 * remounts the note editor); it only listens to keys while `enabled`.
 * Panes are found in the DOM by `data-tui-pane`; list panes register a
 * handle that runs list commands (cursor moves, new, delete, …).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useNavigate, useParams } from 'react-router';
import TuiHelp from './TuiHelp';
import { digitFkey, ESC_DIGIT_WINDOW_MS, nextPane, resolveKey } from './keys';
import type { ListCommand, ListPane, Pane, TuiAction } from './keys';

export interface ListHandle {
  run: (command: ListCommand) => void;
}

type FocusTarget = Pane | 'tags';

interface TuiContextValue {
  enabled: boolean;
  /** The pane with the highlighted (double) border. */
  pane: Pane;
  /** Make `target` the active pane and move keyboard focus into it. */
  focus: (target: FocusTarget) => void;
  registerList: (pane: ListPane, handle: ListHandle | null) => void;
  /** Send a command to a list pane (no-op when it is not mounted). */
  runList: (pane: ListPane, command: ListCommand) => void;
  runFkey: (n: number) => void;
  menuOpen: boolean;
  setMenuOpen: (open: boolean) => void;
  helpOpen: boolean;
  setHelpOpen: (open: boolean) => void;
  notebooksHidden: boolean;
  visiblePanes: Pane[];
}

const TuiContext = createContext<TuiContextValue | null>(null);

/** Selector of the element that takes keyboard focus for each target. */
const FOCUS_SELECTORS: Record<FocusTarget, string> = {
  notebooks: '[data-tui-pane="notebooks"] [data-tui-focus]',
  notes: '[data-tui-pane="notes"] [data-tui-focus]',
  editor: '[data-tui-pane="editor"] [contenteditable="true"]',
  tags: '[data-tui-pane="editor"] input[aria-label="Add tag"]',
};

/** Frames to wait for a target that is still loading (e.g. the editor). */
const FOCUS_RETRY_FRAMES = 60;

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  return (
    target.isContentEditable ||
    !!target.closest('[contenteditable="true"], [contenteditable=""]') ||
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  );
}

function isControl(target: EventTarget | null): boolean {
  return target instanceof HTMLElement && !!target.closest('button, a[href]');
}

/** A dialog not owned by the TUI controller (share, confirm, import, debug) is open. */
function foreignDialogOpen(): boolean {
  return !!document.querySelector('.modal-overlay, .fullscreen-panel');
}

export function TuiProvider({
  enabled,
  visiblePanes,
  notebooksHidden,
  toggleNotebooks,
  children,
}: {
  enabled: boolean;
  visiblePanes: Pane[];
  notebooksHidden: boolean;
  toggleNotebooks: () => void;
  children: React.ReactNode;
}) {
  const { notebookId, noteId } = useParams();
  const navigate = useNavigate();
  const [pane, setPane] = useState<Pane>(notebookId ? 'notes' : 'notebooks');
  const [focusRequest, setFocusRequest] = useState<{ target: FocusTarget; seq: number } | null>(
    null,
  );
  const [menuOpen, setMenuOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const lists = useRef<Partial<Record<ListPane, ListHandle>>>({});
  const escAt = useRef(0);

  const registerList = useCallback((target: ListPane, handle: ListHandle | null) => {
    if (handle) lists.current[target] = handle;
    else delete lists.current[target];
  }, []);

  const runList = useCallback((target: ListPane, command: ListCommand) => {
    lists.current[target]?.run(command);
  }, []);

  const focus = useCallback((target: FocusTarget) => {
    setPane(target === 'tags' ? 'editor' : target);
    setFocusRequest((prev) => ({ target, seq: (prev?.seq ?? 0) + 1 }));
  }, []);

  // Move DOM focus for the latest request, waiting a few frames for targets
  // that are not rendered yet (the editor while its note loads).
  useEffect(() => {
    if (!enabled || !focusRequest) return;
    const { target } = focusRequest;
    let frame = 0;
    let handle = 0;
    const attempt = () => {
      const el = document.querySelector<HTMLElement>(FOCUS_SELECTORS[target]);
      if (el) {
        if (!el.contains(document.activeElement)) el.focus();
        return;
      }
      if (frame++ < FOCUS_RETRY_FRAMES) handle = requestAnimationFrame(attempt);
    };
    attempt();
    return () => cancelAnimationFrame(handle);
  }, [enabled, focusRequest]);

  // Take focus once when the TUI turns on.
  useEffect(() => {
    if (enabled) focus(notebookId ? 'notes' : 'notebooks');
    // Only on enable; later URL changes keep the current pane.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  // Clicking or tabbing into a pane makes it the active one.
  useEffect(() => {
    if (!enabled) return;
    const onFocusIn = (e: FocusEvent) => {
      const owner = (e.target as HTMLElement | null)?.closest?.('[data-tui-pane]');
      const target = owner?.getAttribute('data-tui-pane') as Pane | undefined;
      if (target) setPane(target);
    };
    document.addEventListener('focusin', onFocusIn);
    return () => document.removeEventListener('focusin', onFocusIn);
  }, [enabled]);

  // A hidden pane (notebooks toggled off, note closed) hands over to a visible one.
  const activePane = visiblePanes.includes(pane)
    ? pane
    : visiblePanes.includes('notes')
      ? 'notes'
      : 'notebooks';

  const runFkey = useCallback(
    (n: number) => {
      const target: ListPane = activePane === 'notebooks' ? 'notebooks' : 'notes';
      switch (n) {
        case 1:
          setHelpOpen(true);
          break;
        case 2:
          runList(target, activePane === 'editor' ? 'shareOpen' : 'share');
          break;
        case 3:
          if (notebookId) toggleNotebooks();
          break;
        case 4:
          if (activePane === 'notes') runList('notes', 'open');
          else if (noteId) focus('editor');
          break;
        case 5:
          if (noteId) focus('tags');
          break;
        case 6:
          if (activePane !== 'editor') runList(activePane, 'filter');
          break;
        case 7:
          if (activePane === 'notebooks') runList('notebooks', 'new');
          else if (notebookId) runList('notes', 'new');
          break;
        case 8:
          runList(target, activePane === 'editor' ? 'deleteOpen' : 'delete');
          break;
        case 9:
          setMenuOpen(true);
          break;
        case 10:
          navigate({ search: '?layout=auto' });
          break;
      }
    },
    [activePane, notebookId, noteId, toggleNotebooks, focus, runList, navigate],
  );

  const dispatch = useCallback(
    (action: TuiAction, target: EventTarget | null) => {
      switch (action.type) {
        case 'fkey':
          runFkey(action.n);
          break;
        case 'list':
          if (activePane !== 'editor') runList(activePane, action.command);
          break;
        case 'pane':
          focus(nextPane(activePane, action.to, visiblePanes));
          break;
        case 'escape':
          escAt.current = Date.now();
          if (isTypingTarget(target) || activePane === 'editor') {
            (target as HTMLElement | null)?.blur?.();
            focus(notebookId ? 'notes' : 'notebooks');
          }
          break;
      }
    },
    [activePane, visiblePanes, notebookId, runFkey, runList, focus],
  );

  useEffect(() => {
    if (!enabled) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.defaultPrevented || menuOpen || helpOpen || foreignDialogOpen()) return;

      // mc convention: Esc then a digit is an F-key.
      const armed = Date.now() - escAt.current < ESC_DIGIT_WINDOW_MS;
      escAt.current = 0;
      const escDigit = armed ? digitFkey(e.code) : null;
      if (escDigit !== null && !e.altKey && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        runFkey(escDigit);
        return;
      }

      const action = resolveKey(e, { typing: isTypingTarget(e.target) });
      if (!action) return;
      // Enter on a focused button or link activates it.
      if (action.type === 'list' && isControl(e.target)) return;
      e.preventDefault();
      dispatch(action, e.target);
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [enabled, menuOpen, helpOpen, dispatch, runFkey]);

  const value = useMemo<TuiContextValue>(
    () => ({
      enabled,
      pane: activePane,
      focus,
      registerList,
      runList,
      runFkey,
      menuOpen,
      setMenuOpen,
      helpOpen,
      setHelpOpen,
      notebooksHidden,
      visiblePanes,
    }),
    [
      enabled,
      activePane,
      focus,
      registerList,
      runList,
      runFkey,
      menuOpen,
      helpOpen,
      notebooksHidden,
      visiblePanes,
    ],
  );

  const closeHelp = useCallback(() => {
    setHelpOpen(false);
    focus(activePane);
  }, [focus, activePane]);

  return (
    <TuiContext.Provider value={value}>
      {children}
      {enabled && helpOpen && <TuiHelp onClose={closeHelp} />}
    </TuiContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTui(): TuiContextValue {
  const value = useContext(TuiContext);
  if (!value) throw new Error('useTui must be used inside TuiProvider');
  return value;
}

/** Register `handle` as the command target of a list pane while mounted. */
// eslint-disable-next-line react-refresh/only-export-components
export function useTuiList(pane: ListPane, handle: ListHandle): void {
  const { registerList } = useTui();
  const handleRef = useRef(handle);
  useEffect(() => {
    handleRef.current = handle;
  });
  useEffect(() => {
    registerList(pane, { run: (command) => handleRef.current.run(command) });
    return () => registerList(pane, null);
  }, [pane, registerList]);
}
