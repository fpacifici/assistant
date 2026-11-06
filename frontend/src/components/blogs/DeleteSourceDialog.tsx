/** Deleting a source: all of it, or archive it and keep its useful posts. */

import { useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { deleteSource, fetchSource } from '../../api/blogs';
import type { BlogSource } from '../../types';

interface DeleteSourceDialogProps {
  source: BlogSource;
  onClose: () => void;
}

function usefulPostsLabel(count: number): string {
  return count === 1 ? '1 useful post' : `${count} useful posts`;
}

export default function DeleteSourceDialog({ source, onClose }: DeleteSourceDialogProps) {
  const queryClient = useQueryClient();
  // Outside the ['blogs'] prefix: invalidating that after the delete must not
  // refetch a source that is gone.
  const { data: detail } = useQuery({
    queryKey: ['blog-source', source.id],
    queryFn: () => fetchSource(source.id),
  });
  const usefulCount = detail?.useful_post_count;

  const remove = useMutation({
    mutationFn: (keepUseful: boolean) => deleteSource(source.id, keepUseful),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['blogs'] });
      onClose();
    },
  });

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-label={`Delete ${source.title}`}
        onClick={(e) => e.stopPropagation()}
      >
        <p className="confirm-message">
          Delete “{source.title}”?{' '}
          {usefulCount !== undefined && usefulCount !== null && (
            <>It has {usefulPostsLabel(usefulCount)}.</>
          )}
        </p>
        {remove.isError && <p className="auth-error">Could not delete this source.</p>}
        <div className="delete-source-actions">
          <button
            type="button"
            className="btn-secondary"
            disabled={!usefulCount || remove.isPending}
            onClick={() => remove.mutate(true)}
          >
            Keep useful posts
          </button>
          <button
            type="button"
            className="btn-danger"
            disabled={remove.isPending}
            onClick={() => remove.mutate(false)}
          >
            Delete everything
          </button>
          <button type="button" className="btn-cancel" onClick={onClose}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}
