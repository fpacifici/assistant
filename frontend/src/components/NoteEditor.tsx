import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router';
import { useCreateBlockNote } from '@blocknote/react';
import { BlockNoteView } from '@blocknote/mantine';
import '@blocknote/mantine/style.css';
import { fetchNodes } from '../api/nodes';
import { fetchNote } from '../api/notes';
import { ServerRegistry } from '../markdown/serverRegistry';
import { buildBlocksFromNodes, buildSnapshot } from '../markdown/mapper';
import { executeSave } from '../markdown/reconcile';
import MarkdownToolbar from './MarkdownToolbar';
import AttachmentList from './AttachmentList';
import TagEditor from './TagEditor';
import DebugBlockView from './DebugBlockView';
import ShareDialog from './ShareDialog';
import { TopBarActions } from './TopBarSlot';
import { useTopBarMenuItems } from './TopBarMenuContext';
import { useIsMobile } from '../layout/LayoutModeContext';
import { useTheme } from '../theme/ThemeContext';
import { useUnsavedChangesGuard } from '../hooks/useUnsavedChangesGuard';
import { useAutoSave } from '../hooks/useAutoSave';
import type { NoteNode } from '../types';

const NOTE_ROLE_OPTIONS = ['note_viewer', 'note_editor', 'note_owner'];

export default function NoteEditor() {
  const { notebookId, noteId } = useParams();
  const isMobile = useIsMobile();
  const { theme } = useTheme();
  const queryClient = useQueryClient();
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugTick, setDebugTick] = useState(0);
  const [sharing, setSharing] = useState(false);

  const registry = useRef(new ServerRegistry());
  const snapshotRef = useRef<Map<string, string>>(new Map());
  const [attachmentNodes, setAttachmentNodes] = useState<NoteNode[]>([]);

  const editor = useCreateBlockNote();

  const { data: note } = useQuery({
    queryKey: ['note', notebookId, noteId],
    queryFn: () => fetchNote(notebookId!, noteId!),
    enabled: !!notebookId && !!noteId,
  });

  const { data: nodes, isLoading } = useQuery({
    queryKey: ['nodes', notebookId, noteId],
    queryFn: () => fetchNodes(notebookId!, noteId!),
    enabled: !!notebookId && !!noteId,
  });

  const canUpdate = note?.permissions.includes('update') ?? false;
  const canShare = note?.permissions.includes('share_note') ?? false;

  useEffect(() => {
    editor.isEditable = canUpdate;
  }, [editor, canUpdate]);

  const save = useCallback(async () => {
    if (!notebookId || !noteId) return;
    snapshotRef.current = await executeSave(
      notebookId,
      noteId,
      editor,
      registry.current,
      snapshotRef.current,
    );
    // The registry already tracks the new server nodes. Refetching would
    // replace the blocks under the cursor, so only mark the cache stale.
    queryClient.invalidateQueries({
      queryKey: ['nodes', notebookId, noteId],
      refetchType: 'none',
    });
    // The saved note moves to the top of the list with a fresh preview.
    queryClient.invalidateQueries({ queryKey: ['notes', notebookId] });
  }, [notebookId, noteId, editor, queryClient]);

  const [conflict, setConflict] = useState(false);
  const autoSave = useAutoSave(save, { enabled: canUpdate && !conflict });
  const { markDirty, reset: resetAutoSave } = autoSave;

  useEffect(() => {
    const err = autoSave.error;
    if (err instanceof Error && err.message.includes('409')) setConflict(true);
  }, [autoSave.error]);

  // Load server nodes into the BlockNote editor; keep attachments separate
  useEffect(() => {
    if (!nodes) return;

    const contentNodes = nodes.filter((n) => n.node_type !== 'attachment');
    setAttachmentNodes(nodes.filter((n) => n.node_type === 'attachment'));

    const blocks = buildBlocksFromNodes(contentNodes, editor, registry.current);
    if (blocks.length === 0) {
      editor.replaceBlocks(editor.document, [{ type: 'paragraph', content: [] }]);
      snapshotRef.current = new Map();
    } else {
      editor.replaceBlocks(editor.document, blocks as Parameters<typeof editor.replaceBlocks>[1]);
      snapshotRef.current = buildSnapshot(editor.document, editor);
    }
    resetAutoSave();
    setConflict(false);
  // editor is stable across renders; nodes is the real dependency
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes]);

  // Track changes made by the user
  useEffect(() => {
    const unsubscribe = editor.onChange(() => {
      markDirty();
      setDebugTick((t) => t + 1);
    });
    return unsubscribe;
  }, [editor, markDirty]);

  const handleAttached = useCallback((node: NoteNode) => {
    setAttachmentNodes((prev) => [...prev, node]);
  }, []);

  // On mobile, Share and Debug live in the top bar's ⋯ menu.
  const menuItems = useMemo(() => {
    if (!isMobile) return [];
    const items = [
      {
        id: 'debug',
        label: debugOpen ? 'Hide Debug' : 'Debug',
        onSelect: () => setDebugOpen((prev) => !prev),
      },
    ];
    if (canShare) items.unshift({ id: 'share', label: 'Share', onSelect: () => setSharing(true) });
    return items;
  }, [isMobile, canShare, debugOpen]);
  useTopBarMenuItems(menuItems);

  const unsavedChangesDialog = useUnsavedChangesGuard(
    autoSave.isDirty || autoSave.saving,
    autoSave.flush,
  );

  if (!notebookId || !noteId) {
    return <div className="editor-placeholder">Select a note to edit</div>;
  }

  if (isLoading) return <div>Loading...</div>;

  const saveError = autoSave.error;
  let errorMessage: string | null = null;
  if (conflict) {
    errorMessage = 'Conflict: note was modified externally. Please refresh.';
  } else if (saveError) {
    errorMessage = `Error: ${saveError instanceof Error ? saveError.message : String(saveError)}`;
  }
  let saveState: string | null = null;
  if (autoSave.saving) saveState = 'Saving…';
  else if (errorMessage) saveState = 'Not saved';
  else if (autoSave.isDirty) saveState = 'Unsaved changes';
  else if (canUpdate) saveState = 'Saved';
  const saveIndicator = saveState && (
    <span
      className={`save-state${errorMessage ? ' error' : ''}`}
      data-testid="save-state"
      aria-live="polite"
    >
      {saveState}
    </span>
  );

  // Keep the children in fixed slots for both modes so BlockNoteView is never
  // remounted when the layout mode switches.
  return (
    <div className="note-editor">
      {isMobile && errorMessage && (
        <div className="editor-status" role="status">
          <span className="status error">{errorMessage}</span>
        </div>
      )}
      <MarkdownToolbar
        editor={editor}
        notebookId={notebookId}
        noteId={noteId}
        onAttached={handleAttached}
      />
      {note && <TagEditor notebookId={notebookId} noteId={noteId} tags={note.tags} />}
      <div className={`editor-content${debugOpen && !isMobile ? ' with-debug' : ''}`}>
        <BlockNoteView
          editor={editor}
          theme={theme}
          portalElements={{ default: null }}
        />
        {debugOpen && !isMobile && (
          <DebugBlockView
            key={debugTick}
            blocks={editor.document}
            editor={editor}
            registry={registry.current}
          />
        )}
      </div>
      <AttachmentList nodes={attachmentNodes} />
      {!isMobile && (
        <div className="editor-toolbar">
          {saveIndicator}
          <button
            className="debug-toggle"
            onClick={() => setDebugOpen((prev) => !prev)}
          >
            {debugOpen ? 'Hide Debug' : 'Debug'}
          </button>
          {canShare && (
            <button className="share-btn" onClick={() => setSharing(true)}>
              Share
            </button>
          )}
          {errorMessage && (
            <span className="status error" role="status">{errorMessage}</span>
          )}
        </div>
      )}
      {isMobile && (
        <TopBarActions>{saveIndicator}</TopBarActions>
      )}
      {isMobile && debugOpen && (
        <div className="fullscreen-panel" role="dialog" aria-label="Debug blocks">
          <div className="fullscreen-panel-header">
            <button onClick={() => setDebugOpen(false)}>Close</button>
          </div>
          <DebugBlockView
            key={debugTick}
            blocks={editor.document}
            editor={editor}
            registry={registry.current}
          />
        </div>
      )}
      {sharing && notebookId && noteId && (
        <ShareDialog
          subjectType="note"
          notebookId={notebookId}
          noteId={noteId}
          roleOptions={NOTE_ROLE_OPTIONS}
          onClose={() => setSharing(false)}
        />
      )}
      {unsavedChangesDialog}
    </div>
  );
}
