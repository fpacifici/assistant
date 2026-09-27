/**
 * App shell for the note views. URL params drive visibility.
 *
 * Desktop: header, sidebar (notebooks + notes) and main area (editor).
 * Mobile: top bar and only the deepest URL level — notebook list, note list
 * or editor. Both modes share one component tree so that `NoteEditor` keeps
 * its identity (and unsaved edits) when the mode switches.
 */

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
import { fetchNotebooks } from '../api/notebooks';
import { fetchNote } from '../api/notes';

function useMobileTitle(enabled: boolean): string {
  const { notebookId, noteId } = useParams();

  // Same keys and fetchers as NotebookList / NoteEditor, so these share their cache.
  const { data: notebooks } = useQuery({
    queryKey: ['notebooks'],
    queryFn: fetchNotebooks,
    enabled: enabled && !!notebookId && !noteId,
  });
  const { data: note } = useQuery({
    queryKey: ['note', notebookId, noteId],
    queryFn: () => fetchNote(notebookId!, noteId!),
    enabled: enabled && !!notebookId && !!noteId,
  });

  if (noteId) return note?.title ?? 'Note';
  if (notebookId) return notebooks?.find((nb) => nb.id === notebookId)?.name ?? 'Notes';
  return 'Notebooks';
}

export default function Layout() {
  const { notebookId, noteId } = useParams();
  const mode = useLayoutMode();
  const mobile = mode === 'mobile';
  const title = useMobileTitle(mobile);

  const backTo = noteId
    ? `/notebooks/${notebookId}/notes`
    : notebookId
      ? '/notebooks'
      : undefined;

  // On mobile only the deepest URL level is shown.
  const showSidebar = !mobile || !noteId;
  const showNotebookList = !mobile || !notebookId;
  const showNoteList = !!notebookId && (!mobile || !noteId);
  const showMain = !mobile || !!noteId;

  return (
    <TopBarMenuProvider>
      <TopBarSlotProvider>
        <div className="app-shell" data-layout={mode}>
          {mobile ? <MobileTopBar title={title} backTo={backTo} /> : <DesktopHeader />}
          <div className="layout">
            {showSidebar && (
              <div key="sidebar" className="sidebar">
                {showNotebookList && <NotebookList />}
                {showNoteList && <NoteList />}
              </div>
            )}
            {showMain && (
              <div key="main" className="main">
                {noteId ? <NoteEditor /> : (
                  <div className="editor-placeholder">
                    {notebookId ? 'Select a note to edit' : 'Select a notebook to get started'}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </TopBarSlotProvider>
    </TopBarMenuProvider>
  );
}
