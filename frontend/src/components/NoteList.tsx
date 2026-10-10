/**
 * List of notes within the selected notebook: date, title, a short preview
 * and tags per note. Create/delete via React Query mutations.
 *
 * Notes come most recently updated first, `PAGE_SIZE` at a time; the next
 * page loads when the user scrolls to the end of the list.
 */

import { useMemo, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router';
import { fetchNotes, createNote, deleteNote } from '../api/notes';
import { fetchNotebook } from '../api/notebooks';
import { nextPageOffset } from '../api/pagination';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';
import type { Note, Tag } from '../types';
import ShareDialog from './ShareDialog';
import ConfirmDialog from './ConfirmDialog';

const NOTE_ROLE_OPTIONS = ['note_viewer', 'note_editor', 'note_owner'];
const MAX_VISIBLE_TAGS = 3;

/** Read-only chips for a note's tags; extra tags collapse into a `+N` chip. */
function NoteTags({ tags }: { tags: Tag[] }) {
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

/** "May 11" this year, "May 11, 2025" otherwise; "" for a missing or bad timestamp. */
export function formatNoteDate(timestamp: string, now: Date = new Date()): string {
  const date = new Date(timestamp);
  if (!timestamp || Number.isNaN(date.getTime())) return '';
  const options: Intl.DateTimeFormatOptions = { month: 'short', day: 'numeric' };
  if (date.getFullYear() !== now.getFullYear()) options.year = 'numeric';
  return date.toLocaleDateString(undefined, options);
}

export default function NoteList() {
  const { notebookId, noteId } = useParams();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [newTitle, setNewTitle] = useState('');
  const [sharingNoteId, setSharingNoteId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Note | null>(null);

  const { data, isLoading, hasNextPage, isFetchingNextPage, fetchNextPage } = useInfiniteQuery({
    queryKey: ['notes', notebookId],
    queryFn: ({ pageParam }) => fetchNotes(notebookId!, pageParam),
    initialPageParam: 0,
    getNextPageParam: nextPageOffset,
    enabled: !!notebookId,
  });
  const notes = useMemo(() => data?.pages.flat() ?? [], [data]);
  const sentinelRef = useInfiniteScroll(() => void fetchNextPage());

  // Same key as Layout's mobile title, so they share the cache.
  const { data: notebook } = useQuery({
    queryKey: ['notebook', notebookId],
    queryFn: () => fetchNotebook(notebookId!),
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
      <h3 className="note-list-title">{notebook?.name ?? 'Notes'}</h3>
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
              <span className="note-date">{formatNoteDate(note.update_timestamp)}</span>
              <span className="item-name">{note.title || 'Untitled'}</span>
              {note.preview && <span className="note-preview">{note.preview}</span>}
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
        {hasNextPage && !isFetchingNextPage && (
          <li ref={sentinelRef} className="list-sentinel" aria-hidden="true" />
        )}
      </ul>
      {isFetchingNextPage && <p className="list-loading-more">Loading more...</p>}
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
