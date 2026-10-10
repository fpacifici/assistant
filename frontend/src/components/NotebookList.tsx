/**
 * Sidebar list of notebooks with create/delete/import. Navigates to the
 * selected notebook's notes. Import is a header button on desktop and a `⋯`
 * menu entry on mobile.
 *
 * Notebooks come sorted by name, `PAGE_SIZE` at a time; the next page loads
 * when the user scrolls to the end of the list.
 */

import { useMemo, useState } from 'react';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router';
import { fetchNotebooks, createNotebook, deleteNotebook } from '../api/notebooks';
import type { Notebook } from '../types';
import ShareDialog from './ShareDialog';
import ConfirmDialog from './ConfirmDialog';
import ImportDialog from './ImportDialog';
import { useTopBarMenuItems } from './TopBarMenuContext';
import { nextPageOffset } from '../api/pagination';
import { useInfiniteScroll } from '../hooks/useInfiniteScroll';

const NOTEBOOK_ROLE_OPTIONS = ['notebook_viewer', 'notebook_editor', 'notebook_owner'];

function NotebookIcon() {
  return (
    <svg className="notebook-icon" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
      <rect x="3" y="1.5" width="10" height="13" rx="1.5" fill="none" stroke="currentColor" />
      <line x1="5.5" y1="1.5" x2="5.5" y2="14.5" stroke="currentColor" />
    </svg>
  );
}

export default function NotebookList() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { notebookId } = useParams();
  const [newName, setNewName] = useState('');
  const [sharingNotebookId, setSharingNotebookId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Notebook | null>(null);
  const [importing, setImporting] = useState(false);

  const menuItems = useMemo(
    () => [
      { id: 'import-evernote', label: 'Import from Evernote', onSelect: () => setImporting(true) },
    ],
    [],
  );
  useTopBarMenuItems(menuItems);

  const { data, isLoading, hasNextPage, isFetchingNextPage, fetchNextPage } = useInfiniteQuery({
    queryKey: ['notebooks'],
    queryFn: ({ pageParam }) => fetchNotebooks(pageParam),
    initialPageParam: 0,
    getNextPageParam: nextPageOffset,
  });
  const notebooks = useMemo(() => data?.pages.flat() ?? [], [data]);
  const sentinelRef = useInfiniteScroll(() => void fetchNextPage());

  const createMutation = useMutation({
    mutationFn: (name: string) => createNotebook(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notebooks'] });
      setNewName('');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteNotebook(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notebooks'] });
    },
  });

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (name) createMutation.mutate(name);
  };

  if (isLoading) return <div>Loading notebooks...</div>;

  return (
    <div className="notebook-list">
      <div className="notebook-list-header">
        <h2>Notebooks</h2>
        <button className="import-btn" onClick={() => setImporting(true)}>
          Import
        </button>
      </div>
      <form onSubmit={handleCreate} className="create-form">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New notebook name"
        />
        <button type="submit" disabled={!newName.trim()}>Create</button>
      </form>
      <ul>
        {notebooks.map((nb) => (
          <li
            key={nb.id}
            className={`notebook-item${nb.id === notebookId ? ' active' : ''}`}
          >
            <span
              className="item-name"
              onClick={() => navigate(`/notebooks/${nb.id}/notes`)}
            >
              <NotebookIcon />
              {nb.name}
            </span>
            <span className="item-actions">
              {nb.permissions.includes('share_notebook') && (
                <button
                  className="share-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSharingNotebookId(nb.id);
                  }}
                  title="Share notebook"
                >
                  share
                </button>
              )}
              {nb.permissions.includes('delete_notebook') && (
                <button
                  className="delete-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    setPendingDelete(nb);
                  }}
                  title="Delete notebook"
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
      {notebooks.length === 0 && <p className="empty">No notebooks yet</p>}
      {pendingDelete && (
        <ConfirmDialog
          message={`Delete notebook "${pendingDelete.name}"? This cannot be undone.`}
          confirmLabel="Delete"
          onConfirm={() => {
            deleteMutation.mutate(pendingDelete.id);
            setPendingDelete(null);
          }}
          onCancel={() => setPendingDelete(null)}
        />
      )}
      {importing && <ImportDialog onClose={() => setImporting(false)} />}
      {sharingNotebookId && (
        <ShareDialog
          subjectType="notebook"
          notebookId={sharingNotebookId}
          roleOptions={NOTEBOOK_ROLE_OPTIONS}
          onClose={() => setSharingNotebookId(null)}
        />
      )}
    </div>
  );
}
