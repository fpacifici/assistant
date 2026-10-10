/**
 * Standalone note window (`/notebooks/:notebookId/notes/:noteId/window`),
 * opened from the editor's "Open in new window" button. Shows only the note
 * editor under a slim title bar — no notebook or note lists.
 */

import { useEffect } from 'react';
import { useParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import NoteEditor from '../components/NoteEditor';
import MobileTopBar from '../components/MobileTopBar';
import { TopBarMenuProvider } from '../components/TopBarMenuContext';
import { TopBarSlotProvider } from '../components/TopBarSlot';
import { useLayoutMode } from '../layout/LayoutModeContext';
import { fetchNote } from '../api/notes';

export default function NoteWindow() {
  const { notebookId, noteId } = useParams();
  const mode = useLayoutMode();

  // Same key and fetcher as NoteEditor, so they share the cache.
  const { data: note } = useQuery({
    queryKey: ['note', notebookId, noteId],
    queryFn: () => fetchNote(notebookId!, noteId!),
    enabled: !!notebookId && !!noteId,
  });
  const title = note ? note.title || 'Untitled' : 'Note';

  useEffect(() => {
    const previous = document.title;
    document.title = title;
    return () => {
      document.title = previous;
    };
  }, [title]);

  return (
    <TopBarMenuProvider>
      <TopBarSlotProvider>
        <div className="app-shell note-window" data-layout={mode}>
          {mode === 'mobile' ? (
            <MobileTopBar title={title} />
          ) : (
            <header className="app-header note-window-header">
              <h1 className="app-title">{title}</h1>
            </header>
          )}
          <div className="layout">
            <div className="main">
              <NoteEditor standalone />
            </div>
          </div>
        </div>
      </TopBarSlotProvider>
    </TopBarMenuProvider>
  );
}
