/** Sidebar list of notes within the selected notebook. Create/delete via React Query mutations. */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router';
import { fetchNotes, createNote, deleteNote } from '../api/notes';

export default function NoteList() {
  const { notebookId, noteId } = useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [newTitle, setNewTitle] = useState('');

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
              className="item-name"
              onClick={() => navigate(`/notebooks/${notebookId}/notes/${note.id}`)}
            >
              {note.title}
            </span>
            <button
              className="delete-btn"
              onClick={(e) => {
                e.stopPropagation();
                deleteMutation.mutate(note.id);
              }}
              title="Delete note"
            >
              x
            </button>
          </li>
        ))}
      </ul>
      {notes.length === 0 && <p className="empty">No notes yet</p>}
    </div>
  );
}
