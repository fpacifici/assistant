/** Sidebar list of notes within the selected notebook. Create/delete via React Query mutations. */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router';
import { fetchNotes, createNote, deleteNote } from '../api/notes';
import type { Note, Tag } from '../types';
import ShareDialog from './ShareDialog';
import ConfirmDialog from './ConfirmDialog';

const NOTE_ROLE_OPTIONS = ['note_viewer', 'note_editor', 'note_owner'];
const MAX_VISIBLE_TAGS = 3;

/** Read-only chips for a note's tags; extra tags collapse into a `+N` chip. */
export function NoteTags({ tags }: { tags: Tag[] }) {
  if (tags.length === 0) return null;
  const visible = tags.slice(0, MAX_VISIBLE_TAGS);
  const hidden = tags.slice(MAX_VISIBLE_TAGS);
  return (
    <span className="note-tags">
      {visible.map((tag) => (
        <span key={tag.id} className="tag-chip compact">{tag.name}</span>
      ))}
      {hidden.length > 0 && (
        <span className="tag-chip compact more" title={hidden.map((t) => t.name).join(', ')}>
          +{hidden.length}
        </span>
      )}
    </span>
  );
}

export default function NoteList() {
  const { notebookId, noteId } = useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [newTitle, setNewTitle] = useState('');
  const [sharingNoteId, setSharingNoteId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Note | null>(null);

  const { data: notes = [], isLoading } = useQuery({
    queryKey: ['notes', notebookId],
    queryFn: () => fetchNotes(notebookId!),
    enabled: !!notebookId,
  });

  const createMutation = useMutation({
    mutationFn: (title: string) => createNote(notebookId!, title),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes', notebookId] });
      setNewTitle('');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteNote(notebookId!, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes', notebookId] });
    },
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    const title = newTitle.trim();
    if (title) createMutation.mutate(title);
  };

  if (!notebookId) return null;
  if (isLoading) return <div>Loading notes...</div>;

  return (
    <div className="note-list">
      <h3>Notes</h3>
      <form onSubmit={handleCreate} className="create-form">
        <input
          type="text"
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="New note title"
        />
        <button type="submit" disabled={!newTitle.trim()}>Create</button>
      </form>
      <ul>
        {notes.map((note) => (
          <li
            key={note.id}
            className={`note-item${note.id === noteId ? ' active' : ''}`}
          >
            <span
              className="item-main"
              onClick={() => navigate(`/notebooks/${notebookId}/notes/${note.id}`)}
            >
              <span className="item-name">{note.title}</span>
              <NoteTags tags={note.tags} />
            </span>
            <span className="item-actions">
              {note.permissions.includes('share_note') && (
                <button
                  className="share-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSharingNoteId(note.id);
                  }}
                  title="Share note"
                >
                  share
                </button>
              )}
              {note.permissions.includes('delete_note') && (
                <button
                  className="delete-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setPendingDelete(note);
                  }}
                  title="Delete note"
                >
                  x
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>
      {notes.length === 0 && <p className="empty">No notes yet</p>}
      {pendingDelete && (
        <ConfirmDialog
          message={`Delete note "${pendingDelete.title}"? This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={() => {
            deleteMutation.mutate(pendingDelete.id);
            setPendingDelete(null);
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
      {sharingNoteId && (
        <ShareDialog
          subjectType="note"
          notebookId={notebookId}
          noteId={sharingNoteId}
          roleOptions={NOTE_ROLE_OPTIONS}
          onClose={() => setSharingNoteId(null)}
        />
      )}
    </div>
  );
}
