/** Two-panel layout: sidebar (notebooks + notes) and main area (editor). URL params drive visibility. */

import { useParams } from 'react-router';
import NotebookList from './NotebookList';
import NoteList from './NoteList';
import NoteEditor from './NoteEditor';

export default function Layout() {
  const { notebookId, noteId } = useParams();

  return (
    <div className="layout">
      <div className="sidebar">
        <NotebookList />
        {notebookId && <NoteList />}
      </div>
      <div className="main">
        {noteId ? <NoteEditor /> : (
          <div className="editor-placeholder">
            {notebookId ? 'Select a note to edit' : 'Select a notebook to get started'}
          </div>
        )}
      </div>
    </div>
  );
}
