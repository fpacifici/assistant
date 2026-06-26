import { useState, useEffect, useRef, useCallback } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router';
import { useCreateBlockNote } from '@blocknote/react';
import { BlockNoteView } from '@blocknote/mantine';
import '@blocknote/mantine/style.css';
import { fetchNodes } from '../api/nodes';
import { ServerRegistry } from '../markdown/serverRegistry';
import { buildBlocksFromNodes, buildSnapshot } from '../markdown/mapper';
import { executeSave } from '../markdown/reconcile';
import { useUser } from '../contexts/UserContext';
import MarkdownToolbar from './MarkdownToolbar';

export default function NoteEditor() {
  const { notebookId, noteId } = useParams();
  const queryClient = useQueryClient();
  const { userId } = useUser();
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [isDirty, setIsDirty] = useState(false);

  const registry = useRef(new ServerRegistry());
  const snapshotRef = useRef<Map<string, string>>(new Map());

  const editor = useCreateBlockNote();

  const { data: nodes, isLoading } = useQuery({
    queryKey: ['nodes', notebookId, noteId],
    queryFn: () => fetchNodes(notebookId!, noteId!),
    enabled: !!notebookId && !!noteId,
  });

  // Load server nodes into the BlockNote editor
  useEffect(() => {
    if (!nodes) return;

    const blocks = buildBlocksFromNodes(nodes, editor, registry.current);
    if (blocks.length === 0) {
      editor.replaceBlocks(editor.document, [{ type: 'paragraph', content: [] }]);
      snapshotRef.current = new Map();
    } else {
      editor.replaceBlocks(editor.document, blocks as Parameters<typeof editor.replaceBlocks>[1]);
      snapshotRef.current = buildSnapshot(editor.document, editor);
    }
    setIsDirty(false);
    setStatus(null);
  // editor is stable across renders; nodes is the real dependency
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes]);

  // Track changes made by the user
  useEffect(() => {
    const unsubscribe = editor.onChange(() => {
      setIsDirty(true);
      setStatus(null);
    });
    return unsubscribe;
  }, [editor]);

  const handleSave = useCallback(async () => {
    if (!notebookId || !noteId) return;
    setSaving(true);
    setStatus(null);

    try {
      const newSnapshot = await executeSave(
        notebookId,
        noteId,
        editor,
        registry.current,
        snapshotRef.current,
        userId,
      );
      snapshotRef.current = newSnapshot;
      setIsDirty(false);
      setStatus('Saved');
      queryClient.invalidateQueries({ queryKey: ['nodes', notebookId, noteId] });
    } catch (err) {
      if (err instanceof Error && err.message.includes('409')) {
        setStatus('Conflict: note was modified externally. Please refresh.');
      } else {
        setStatus(`Error: ${err instanceof Error ? err.message : String(err)}`);
      }
    } finally {
      setSaving(false);
    }
  }, [notebookId, noteId, editor, userId, queryClient]);

  if (!notebookId || !noteId) {
    return <div className="editor-placeholder">Select a note to edit</div>;
  }

  if (isLoading) return <div>Loading...</div>;

  return (
    <div className="note-editor">
      <MarkdownToolbar editor={editor} />
      <div className="editor-content">
        <BlockNoteView
          editor={editor}
          theme="light"
          portalElements={{ default: null }}
        />
      </div>
      <div className="editor-toolbar">
        <button onClick={handleSave} disabled={!isDirty || saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
        {status && (
          <span
            className={`status ${
              status.startsWith('Error') || status.startsWith('Conflict') ? 'error' : 'success'
            }`}
          >
            {status}
          </span>
        )}
      </div>
    </div>
  );
}
