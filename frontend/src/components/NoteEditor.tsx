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
import DebugBlockView from './DebugBlockView';
import ShareDialog from './ShareDialog';
import { TopBarActions } from './TopBarSlot';
import { useTopBarMenuItems } from './TopBarMenuContext';
import { useIsMobile } from '../layout/LayoutModeContext';
import type { NoteNode } from '../types';

const NOTE_ROLE_OPTIONS = ['note_viewer', 'note_editor', 'note_owner'];

export default function NoteEditor() {
  const { notebookId, noteId } = useParams();
  const isMobile = useIsMobile();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
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
      setDebugTick((t) => t + 1);
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
  }, [notebookId, noteId, editor, queryClient]);

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

  if (!notebookId || !noteId) {
    return <div className="editor-placeholder">Select a note to edit</div>;
  }

  if (isLoading) return <div>Loading...</div>;

  const saveDisabled = !isDirty || saving || !canUpdate;
  const saveLabel = saving ? 'Saving...' : 'Save';
  const statusLine = status && (
    <span
      className={`status ${
        status.startsWith('Error') || status.startsWith('Conflict') ? 'error' : 'success'
      }`}
    >
      {status}
    </span>
  );

  // Keep the children in fixed slots for both modes so BlockNoteView is never
  // remounted when the layout mode switches.
  return (
    <div className="note-editor">
      {isMobile && status && (
        <div className="editor-status" role="status">{statusLine}</div>
      )}
      <MarkdownToolbar
        editor={editor}
        notebookId={notebookId}
        noteId={noteId}
        onAttached={handleAttached}
      />
      <div className={`editor-content${debugOpen && !isMobile ? ' with-debug' : ''}`}>
        <BlockNoteView
          editor={editor}
          theme="light"
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
          <button onClick={handleSave} disabled={saveDisabled}>
            {saveLabel}
          </button>
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
          {statusLine}
        </div>
      )}
      {isMobile && (
        <TopBarActions>
          <button onClick={handleSave} disabled={saveDisabled}>
            {saveLabel}
          </button>
        </TopBarActions>
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
    </div>
  );
}
