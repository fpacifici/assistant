/** The user's Ask AI threads, most recent first, with New chat and delete. */

import { useState } from 'react';
import { Link } from 'react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { deleteThread, listThreads } from '../api/ask';
import type { ChatThread } from '../api/ask';
import ConfirmDialog from './ConfirmDialog';

interface AskThreadListProps {
  activeId: string | null;
  /** Called after the active thread was deleted. */
  onActiveDeleted: () => void;
}

function threadTitle(thread: ChatThread): string {
  return thread.title || 'New chat';
}

export default function AskThreadList({ activeId, onActiveDeleted }: AskThreadListProps) {
  const queryClient = useQueryClient();
  const [deleting, setDeleting] = useState<ChatThread | null>(null);
  const { data: threads = [], isLoading } = useQuery({
    queryKey: ['ask', 'threads'],
    queryFn: listThreads,
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteThread(id),
    onSuccess: (_data, id) => {
      queryClient.removeQueries({ queryKey: ['ask', 'thread', id] });
      void queryClient.invalidateQueries({ queryKey: ['ask', 'threads'] });
      if (id === activeId) onActiveDeleted();
    },
  });

  return (
    <nav className="ask-threads" aria-label="Chats">
      <Link to="?thread=new" className="ask-new-chat">
        + New chat
      </Link>
      {isLoading && <p className="empty">Loading…</p>}
      {!isLoading && threads.length === 0 && <p className="empty">No chats yet</p>}
      <ul>
        {threads.map((thread) => (
          <li key={thread.id} className={`ask-thread${thread.id === activeId ? ' active' : ''}`}>
            <Link
              to={`?thread=${thread.id}`}
              className="item-name"
              aria-current={thread.id === activeId ? 'page' : undefined}
            >
              {threadTitle(thread)}
            </Link>
            <button
              type="button"
              className="delete-btn"
              aria-label={`Delete chat ${threadTitle(thread)}`}
              onClick={() => setDeleting(thread)}
            >
              &times;
            </button>
          </li>
        ))}
      </ul>
      {remove.isError && <p className="ask-error">Could not delete the chat.</p>}
      {deleting && (
        <ConfirmDialog
          message={`Delete the chat "${threadTitle(deleting)}"?`}
          confirmLabel="Delete"
          onConfirm={() => {
            remove.mutate(deleting.id);
            setDeleting(null);
          }}
          onCancel={() => setDeleting(null)}
        />
      )}
    </nav>
  );
}
