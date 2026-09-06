/** Sidebar list of notebooks with create/delete. Navigates to the selected notebook's notes. */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router';
import { fetchNotebooks, createNotebook, deleteNotebook } from '../api/notebooks';
import ShareDialog from './ShareDialog';

const NOTEBOOK_ROLE_OPTIONS = ['notebook_viewer', 'notebook_editor', 'notebook_owner'];

export default function NotebookList() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { notebookId } = useParams();
  const [newName, setNewName] = useState('');
  const [sharingNotebookId, setSharingNotebookId] = useState<string | null>(null);

  const { data: notebooks = [], isLoading } = useQuery({
    queryKey: ['notebooks'],
    queryFn: fetchNotebooks,
  });

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
      <h2>Notebooks</h2>
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
                    deleteMutation.mutate(nb.id);
                  }}
                  title="Delete notebook"
                >
                  x
                </button>
              )}
            </span>
          </li>
        ))}
      </ul>
      {notebooks.length === 0 && <p className="empty">No notebooks yet</p>}
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
