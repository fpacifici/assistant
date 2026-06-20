import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router';
import { fetchNodes, updateNode } from '../api/nodes';
import type { NoteNode } from '../types';

export default function NoteEditor() {
  const { notebookId, noteId } = useParams();
  const queryClient = useQueryClient();
  const [text, setText] = useState('');
  const [currentNode, setCurrentNode] = useState<NoteNode | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const { data: nodes, isLoading } = useQuery({
    queryKey: ['nodes', notebookId, noteId],
    queryFn: () => fetchNodes(notebookId!, noteId!),
    enabled: !!notebookId && !!noteId,
  });

  useEffect(() => {
    if (nodes && nodes.length > 0) {
      const node = nodes[0];
      setCurrentNode(node);
      setText(node.payload ?? '');
      setStatus(null);
    }
  }, [nodes]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateNode(
        notebookId!,
        noteId!,
        currentNode!.id,
        text,
        currentNode!.version,
      ),
    onSuccess: (updated) => {
      setCurrentNode(updated);
      setStatus('Saved');
      queryClient.invalidateQueries({ queryKey: ['nodes', notebookId, noteId] });
    },
    onError: (err) => {
      if (err instanceof Error && err.message.includes('409')) {
        setStatus('Conflict: note was modified externally. Please refresh.');
      } else {
        setStatus(`Error: ${err.message}`);
      }
    },
  });

  if (!notebookId || !noteId) {
    return <div className="editor-placeholder">Select a note to edit</div>;
  }

  if (isLoading) return <div>Loading...</div>;

  if (!currentNode) {
    return <div className="editor-placeholder">No content</div>;
  }

  const isDirty = text !== (currentNode.payload ?? '');

  return (
    <div className="note-editor">
      <textarea
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setStatus(null);
        }}
      />
      <div className="editor-toolbar">
        <button
          onClick={() => saveMutation.mutate()}
          disabled={!isDirty || saveMutation.isPending}
        >
          {saveMutation.isPending ? 'Saving...' : 'Save'}
        </button>
        {status && <span className={`status ${status.startsWith('Error') || status.startsWith('Conflict') ? 'error' : 'success'}`}>{status}</span>}
      </div>
    </div>
  );
}
