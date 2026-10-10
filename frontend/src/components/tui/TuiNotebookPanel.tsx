/**
 * TUI notebooks pane: same data and mutations as `NotebookList`, driven by
 * a keyboard cursor. Commands arrive from the TUI controller (F-keys,
 * arrows, Enter); a click opens the notebook.
 */

import { useCallback, useMemo, useState } from 'react';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router';
import { createNotebook, deleteNotebook, fetchNotebooks } from '../../api/notebooks';
import { nextPageOffset } from '../../api/pagination';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';
import type { Notebook } from '../../types';
import ConfirmDialog from '../ConfirmDialog';
import ShareDialog from '../ShareDialog';
import TuiBorder from './TuiBorder';
import TuiList from './TuiList';
import { isMoveCommand, useListCursor } from './listCursor';
import TuiPrompt from './TuiPrompt';
import { useTui, useTuiList } from './TuiContext';

const NOTEBOOK_ROLE_OPTIONS = ['notebook_viewer', 'notebook_editor', 'notebook_owner'];

type Dialog =
  | { kind: 'new' }
  | { kind: 'filter' }
  | { kind: 'delete'; notebook: Notebook }
  | { kind: 'share'; notebookId: string };

export default function TuiNotebookPanel() {
  const { notebookId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { pane, focus } = useTui();
  const [filter, setFilter] = useState('');
  const [dialog, setDialog] = useState<Dialog | null>(null);

  const { data, isLoading, hasNextPage, isFetchingNextPage, fetchNextPage } = useInfiniteQuery({
    queryKey: ['notebooks'],
    queryFn: ({ pageParam }) => fetchNotebooks(pageParam),
    initialPageParam: 0,
    getNextPageParam: nextPageOffset,
  });
  const notebooks = useMemo(() => data?.pages.flat() ?? [], [data]);
  const visible = useMemo(() => {
    const needle = filter.toLowerCase();
    return needle ? notebooks.filter((nb) => nb.name.toLowerCase().includes(needle)) : notebooks;
  }, [notebooks, filter]);

  const loadMore = useCallback(() => {
    if (hasNextPage && !isFetchingNextPage) void fetchNextPage();
  }, [hasNextPage, isFetchingNextPage, fetchNextPage]);
  const sentinelRef = useInfiniteScroll(loadMore);
  const cursor = useListCursor(visible, notebookId, loadMore);

  const createMutation = useMutation({
    mutationFn: (name: string) => createNotebook(name),
    onSuccess: (notebook) => {
      queryClient.invalidateQueries({ queryKey: ['notebooks'] });
      navigate(`/notebooks/${notebook.id}/notes`);
      focus('notes');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteNotebook(id),
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['notebooks'] });
      if (id === notebookId) navigate('/notebooks');
    },
  });

  const open = (notebook: Notebook) => {
    cursor.select(notebook.id);
    navigate(`/notebooks/${notebook.id}/notes`);
  };

  useTuiList('notebooks', {
    run: (command) => {
      if (isMoveCommand(command)) {
        cursor.move(command);
        return;
      }
      const current = cursor.current;
      switch (command) {
        case 'open':
          if (current) {
            open(current);
            focus('notes');
          }
          break;
        case 'new':
          setDialog({ kind: 'new' });
          break;
        case 'filter':
          setDialog({ kind: 'filter' });
          break;
        case 'delete':
          if (current?.permissions.includes('delete_notebook')) {
            setDialog({ kind: 'delete', notebook: current });
          }
          break;
        case 'share':
          if (current?.permissions.includes('share_notebook')) {
            setDialog({ kind: 'share', notebookId: current.id });
          }
          break;
      }
    },
  });

  const count = `${visible.length}${hasNextPage ? '+' : ''} notebooks`;
  const footer = filter ? `filter: ${filter} · ${count}` : count;
  const closeDialog = () => {
    setDialog(null);
    focus('notebooks');
  };

  return (
    <div className="tui-panel tui-framed">
      <TuiBorder title="Notebooks" footer={footer} active={pane === 'notebooks'} />
      {isLoading ? (
        <p className="tui-empty">Loading notebooks…</p>
      ) : (
        <TuiList
          label="Notebooks"
          items={visible}
          cursorIndex={cursor.index}
          openId={notebookId}
          emptyText={filter ? 'No match' : 'No notebooks yet — F7 to create one'}
          onActivate={open}
          renderRow={(nb) => <span className="tui-row-title">{nb.name}</span>}
          footer={
            hasNextPage && !isFetchingNextPage && !filter ? (
              <li ref={sentinelRef} className="list-sentinel" aria-hidden="true" />
            ) : null
          }
        />
      )}
      {dialog?.kind === 'new' && (
        <TuiPrompt
          title="New notebook"
          label="Name:"
          onSubmit={(name) => {
            setDialog(null);
            createMutation.mutate(name);
          }}
          onCancel={closeDialog}
        />
      )}
      {dialog?.kind === 'filter' && (
        <TuiPrompt
          title="Filter notebooks"
          label="Name contains:"
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
          message={`Delete notebook "${dialog.notebook.name}"? This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={() => {
            deleteMutation.mutate(dialog.notebook.id);
            closeDialog();
          }}
          onCancel={closeDialog}
        />
      )}
      {dialog?.kind === 'share' && (
        <ShareDialog
          subjectType="notebook"
          notebookId={dialog.notebookId}
          roleOptions={NOTEBOOK_ROLE_OPTIONS}
          onClose={closeDialog}
        />
      )}
    </div>
  );
}
