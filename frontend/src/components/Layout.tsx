/**
 * App shell for the note views. URL params drive visibility.
 *
 * TUI (`?layout=tui`): the desktop columns drawn as text-framed panes, with
 * a menu bar, an F-key bar and keyboard navigation (see `components/tui/`).
 *
 * Desktop: header, then three columns — notebooks, notes (with previews)
 * and the editor. The notebooks column can be hidden while a notebook is
 * open (remembered per browser).
 * Mobile: top bar and only the deepest URL level — notebook list, note list
 * or editor. Both modes share one component tree so that `NoteEditor` keeps
 * its identity (and unsaved edits) when the mode switches.
 */

import { useMemo } from 'react';
import { useParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import NotebookList from './NotebookList';
import NoteList from './NoteList';
import NoteEditor from './NoteEditor';
import DesktopHeader from './DesktopHeader';
import MobileTopBar from './MobileTopBar';
import { TopBarMenuProvider } from './TopBarMenuContext';
import { TopBarSlotProvider } from './TopBarSlot';
import { useLayoutMode } from '../layout/LayoutModeContext';
import { useNotebooksHidden } from '../layout/useNotebooksHidden';
import { fetchNotebook } from '../api/notebooks';
import { fetchNote } from '../api/notes';
import { TuiProvider, useTui } from './tui/TuiContext';
import TuiBorder from './tui/TuiBorder';
import TuiMenuBar from './tui/TuiMenuBar';
import TuiKeyBar from './tui/TuiKeyBar';
import TuiNotebookPanel from './tui/TuiNotebookPanel';
import TuiNotePanel from './tui/TuiNotePanel';
import type { Pane } from './tui/keys';

function useMobileTitle(enabled: boolean): string {
  const { notebookId, noteId } = useParams();

  // Same keys and fetchers as NoteList / NoteEditor, so these share their cache.
  const { data: notebook } = useQuery({
    queryKey: ['notebook', notebookId],
    queryFn: () => fetchNotebook(notebookId!),
    enabled: enabled && !!notebookId && !noteId,
  });
  const { data: note } = useQuery({
    queryKey: ['note', notebookId, noteId],
    queryFn: () => fetchNote(notebookId!, noteId!),
    enabled: enabled && !!notebookId && !!noteId,
  });

  if (noteId) return note?.title ?? 'Note';
  if (notebookId) return notebook?.name ?? 'Notes';
  return 'Notebooks';
}

/** Frame of the editor pane; double lines while it is the active pane. */
function TuiEditorBorder({ title }: { title?: string }) {
  const { pane } = useTui();
  return <TuiBorder title={title ?? 'Editor'} active={pane === 'editor'} />;
}

export default function Layout() {
  const { notebookId, noteId } = useParams();
  const mode = useLayoutMode();
  const mobile = mode === 'mobile';
  const tui = mode === 'tui';
  const title = useMobileTitle(mobile || tui);

  const backTo = noteId
    ? `/notebooks/${notebookId}/notes`
    : notebookId
      ? '/notebooks'
      : undefined;

  const [notebooksHidden, toggleNotebooks] = useNotebooksHidden();

  // Desktop: notebooks | notes | editor columns; the notebooks column can be
  // hidden while a notebook is open. On mobile only the deepest URL level is
  // shown.
  const showNotebookList = mobile ? !notebookId : !(notebooksHidden && notebookId);
  const showNoteList = !!notebookId && (!mobile || !noteId);
  const showMain = !mobile || !!noteId;

  const visiblePanes = useMemo(() => {
    const panes: Pane[] = [];
    if (showNotebookList) panes.push('notebooks');
    if (showNoteList) panes.push('notes');
    if (noteId) panes.push('editor');
    return panes;
  }, [showNotebookList, showNoteList, noteId]);

  let header = <DesktopHeader />;
  if (mobile) header = <MobileTopBar title={title} backTo={backTo} />;
  else if (tui) header = <TuiMenuBar />;

  // The TUI swaps the list components and adds frames around the same
  // columns, so NoteEditor keeps its slot (and unsaved edits) across modes.
  return (
    <TopBarMenuProvider>
      <TopBarSlotProvider>
        <TuiProvider
          enabled={tui}
          visiblePanes={visiblePanes}
          notebooksHidden={notebooksHidden}
          toggleNotebooks={toggleNotebooks}
        >
          <div className={`app-shell${tui ? ' tui' : ''}`} data-layout={mode}>
            {header}
            <div className="layout">
              {showNotebookList && (
                <div key="sidebar" className="sidebar" data-tui-pane="notebooks">
                  {tui ? <TuiNotebookPanel /> : <NotebookList />}
                </div>
              )}
              {showNoteList && (
                <div key="notes" className="notes-column" data-tui-pane="notes">
                  {!mobile && !tui && (
                    <button
                      type="button"
                      className="notebooks-toggle"
                      onClick={toggleNotebooks}
                      aria-label={notebooksHidden ? 'Show notebooks' : 'Hide notebooks'}
                      title={notebooksHidden ? 'Show notebooks' : 'Hide notebooks'}
                    >
                      {notebooksHidden ? '»' : '«'}
                    </button>
                  )}
                  {tui ? <TuiNotePanel /> : <NoteList />}
                </div>
              )}
              {showMain && (
                <div key="main" className="main" data-tui-pane="editor" tabIndex={tui ? -1 : undefined}>
                  {tui && <TuiEditorBorder title={noteId ? title : undefined} />}
                  {noteId ? <NoteEditor /> : (
                    <div className="editor-placeholder">
                      {notebookId ? 'Select a note to edit' : 'Select a notebook to get started'}
                    </div>
                  )}
                </div>
              )}
            </div>
            {tui && <TuiKeyBar />}
          </div>
        </TuiProvider>
      </TopBarSlotProvider>
    </TopBarMenuProvider>
  );
}
