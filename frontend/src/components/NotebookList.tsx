import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router';
import { fetchNotebooks, createNotebook, deleteNotebook } from '../api/notebooks';
import { useUser } from '../contexts/UserContext';

export default function NotebookList() {
  const { userId } = useUser();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { notebookId } = useParams();
  const [newName, setNewName] = useState('');

  const { data: notebooks = [], isLoading } = useQuery({
    queryKey: ['notebooks', userId],
    queryFn: () => fetchNotebooks(userId),
  });

  const createMutation = useMutation({
    mutationFn: (name: string) => createNotebook(userId, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notebooks', userId] });
      setNewName('');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteNotebook(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notebooks', userId] });
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
          </li>
        ))}
      </ul>
      {notebooks.length === 0 && <p className="empty">No notebooks yet</p>}
    </div>
  );
}
