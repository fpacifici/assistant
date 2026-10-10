/**
 * TUI notes pane: the selected notebook's notes (same data and mutations as
 * `NoteList`), driven by a keyboard cursor. Each row is the date and title,
 * then the preview and tags. Enter opens the note in the editor pane.
 */

import { useCallback, useMemo, useState } from 'react';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router';
import { createNote, deleteNote, fetchNote, fetchNotes } from '../../api/notes';
import { fetchNotebook } from '../../api/notebooks';
import { nextPageOffset } from '../../api/pagination';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';
import type { Note } from '../../types';
import ConfirmDialog from '../ConfirmDialog';
import ShareDialog from '../ShareDialog';
import { formatNoteDate } from '../NoteList';
import TuiBorder from './TuiBorder';
import TuiList from './TuiList';
import { isMoveCommand, useListCursor } from './listCursor';
import TuiPrompt from './TuiPrompt';
import { useTui, useTuiList } from './TuiContext';

const NOTE_ROLE_OPTIONS = ['note_viewer', 'note_editor', 'note_owner'];
/** Width of the date column, in characters ("May 11, 2025"). */
const DATE_WIDTH = 12;

type Dialog =
  | { kind: 'new' }
  | { kind: 'filter' }
  | { kind: 'delete'; note: Note }
  | { kind: 'share'; noteId: string };

function NoteRow({ note }: { note: Note }) {
  return (
    <>
      <span className="tui-row-line">
        <span className="tui-row-date">{formatNoteDate(note.update_timestamp).padEnd(DATE_WIDTH)}</span>
        <span className="tui-row-title">{note.title || 'Untitled'}</span>
      </span>
      {(note.preview || note.tags.length > 0) && (
        <span className="tui-row-line tui-row-sub">
          {note.tags.map((tag) => (
            <span key={tag.id} className="tui-tag">#{tag.name} </span>
          ))}
          {note.preview}
        </span>
      )}
    </>
  );
}

export default function TuiNotePanel() {
  const { notebookId, noteId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pane, focus } = useTui();
  const [filter, setFilter] = useState('');
  const [dialog, setDialog] = useState<Dialog | null>(null);

  const { data, isLoading, hasNextPage, isFetchingNextPage, fetchNextPage } = useInfiniteQuery({
    queryKey: ['notes', notebookId],
    queryFn: ({ pageParam }) => fetchNotes(notebookId!, pageParam),
    initialPageParam: 0,
    getNextPageParam: nextPageOffset,
    enabled: !!notebookId,
  });
  const notes = useMemo(() => data?.pages.flat() ?? [], [data]);
  const visible = useMemo(() => {
    const needle = filter.toLowerCase();
    if (!needle) return notes;
    return notes.filter(
      (note) =>
        note.title.toLowerCase().includes(needle) ||
        note.tags.some((tag) => tag.name.toLowerCase().includes(needle)),
    );
  }, [notes, filter]);

  // Same keys as NoteList / NoteEditor, so they share the cache.
  const { data: notebook } = useQuery({
    queryKey: ['notebook', notebookId],
    queryFn: () => fetchNotebook(notebookId!),
    enabled: !!notebookId,
  });
  const { data: openNote } = useQuery({
    queryKey: ['note', notebookId, noteId],
    queryFn: () => fetchNote(notebookId!, noteId!),
    enabled: !!notebookId && !!noteId,
  });

  const loadMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);
  const sentinelRef = useInfiniteScroll(loadMore);
  const cursor = useListCursor(visible, noteId, loadMore);

  const createMutation = useMutation({
    mutationFn: (title: string) => createNote(notebookId!, title),
    onSuccess: (note) => {
      queryClient.invalidateQueries({ queryKey: ['notes', notebookId] });
      navigate(`/notebooks/${notebookId}/notes/${note.id}`);
      focus('editor');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteNote(notebookId!, id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['notes', notebookId] });
      if (id === noteId) navigate(`/notebooks/${notebookId}/notes`);
    },
  });

  const open = (note: Note) => {
    cursor.select(note.id);
    navigate(`/notebooks/${notebookId}/notes/${note.id}`);
  };

  const askDelete = (note: Note | undefined) => {
    if (note?.permissions.includes('delete_note')) setDialog({ kind: 'delete', note });
  };
  const askShare = (note: Note | undefined) => {
    if (note?.permissions.includes('share_note')) setDialog({ kind: 'share', noteId: note.id });
  };

  useTuiList('notes', {
    run: (command) => {
      if (isMoveCommand(command)) {
        cursor.move(command);
        return;
      }
      switch (command) {
        case 'open':
          if (cursor.current) {
            open(cursor.current);
            focus('editor');
          }
          break;
        case 'new':
          setDialog({ kind: 'new' });
          break;
        case 'filter':
          setDialog({ kind: 'filter' });
          break;
        case 'delete':
          askDelete(cursor.current);
          break;
        case 'deleteOpen':
          askDelete(openNote);
          break;
        case 'share':
          askShare(cursor.current);
          break;
        case 'shareOpen':
          askShare(openNote);
          break;
      }
    },
  });

  if (!notebookId) return null;

  const count = `${visible.length}${hasNextPage ? '+' : ''} notes`;
  const footer = filter ? `filter: ${filter} · ${count}` : count;
  const closeDialog = () => {
    setDialog(null);
    focus(pane);
  };

  return (
    <div className="tui-panel tui-framed">
      <TuiBorder title={notebook?.name ?? 'Notes'} footer={footer} active={pane === 'notes'} />
      {isLoading ? (
        <p className="tui-empty">Loading notes…</p>
      ) : (
        <TuiList
          label="Notes"
          items={visible}
          cursorIndex={cursor.index}
          openId={noteId}
          emptyText={filter ? 'No match' : 'No notes yet — F7 to create one'}
          onActivate={open}
          renderRow={(note) => <NoteRow note={note} />}
          footer={
            hasNextPage && !isFetchingNextPage && !filter ? (
              <li ref={sentinelRef} className="list-sentinel" aria-hidden="true" />
            ) : null
          }
        />
      )}
      {dialog?.kind === 'new' && (
        <TuiPrompt
          title="New note"
          label="Title:"
          onSubmit={(title) => {
            setDialog(null);
            createMutation.mutate(title);
          }}
          onCancel={closeDialog}
        />
      )}
      {dialog?.kind === 'filter' && (
        <TuiPrompt
          title="Filter notes"
          label="Title or tag contains:"
          initialValue={filter}
          allowEmpty
          onSubmit={(value) => {
            setFilter(value);
            closeDialog();
          }}
          onCancel={closeDialog}
        />
      )}
      {dialog?.kind === 'delete' && (
        <ConfirmDialog
          message={`Delete note "${dialog.note.title}"? This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={() => {
            deleteMutation.mutate(dialog.note.id);
            setDialog(null);
            focus('notes');
          }}
          onCancel={closeDialog}
        />
      )}
      {dialog?.kind === 'share' && (
        <ShareDialog
          subjectType="note"
          notebookId={notebookId}
          noteId={dialog.noteId}
          roleOptions={NOTE_ROLE_OPTIONS}
          onClose={closeDialog}
        />
      )}
    </div>
  );
}
