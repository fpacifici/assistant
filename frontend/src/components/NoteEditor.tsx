import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { InfiniteData } from '@tanstack/react-query';
import { useNavigate, useParams, useSearchParams } from 'react-router';
import { useCreateBlockNote } from '@blocknote/react';
import { BlockNoteView } from '@blocknote/mantine';
import '@blocknote/mantine/style.css';
import { fetchNodes } from '../api/nodes';
import { fetchNote, updateNoteTitle } from '../api/notes';
import { ServerRegistry } from '../markdown/serverRegistry';
import { buildBlocksFromNodes, buildSnapshot } from '../markdown/mapper';
import { executeSave } from '../markdown/reconcile';
import {
  applyLiveMerge,
  planLiveMerge,
  replaceBlockContent,
  type BlockConflict,
} from '../markdown/liveMerge';
import { localCursor } from '../markdown/cursors';
import { ApiError } from '../api/client';
import PresenceAvatars from './presence/PresenceAvatars';
import RemoteCursors from './presence/RemoteCursors';
import ConflictBar from './presence/ConflictBar';
import { conflictStyle } from './presence/style';
import { useNotePresence } from '../hooks/useNotePresence';
import { useLiveNote } from '../hooks/useLiveNote';
import MarkdownToolbar from './MarkdownToolbar';
import NoteTitle from './NoteTitle';
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
import { noteWindowPath, openNoteWindow } from '../lib/noteWindow';
import type { Note, NoteNode } from '../types';

const NOTE_ROLE_OPTIONS = ['note_viewer', 'note_editor', 'note_owner'];
const SEARCH_HIT_FLASH_MS = 1500;

/**
 * `standalone` is set in the note's own window (`NoteWindow`), which has no
 * "Open in new window" button.
 *
 * The title sits at the top of the text as an H2 (`NoteTitle`) and has its own
 * autosave, joined with the text's for the save state, the unsaved-changes
 * guard and "Open in new window".
 */
export default function NoteEditor({ standalone = false }: { standalone?: boolean }) {
  const { notebookId, noteId } = useParams();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const { colorScheme } = useTheme();
  const queryClient = useQueryClient();
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugTick, setDebugTick] = useState(0);
  const [sharing, setSharing] = useState(false);

  const registry = useRef(new ServerRegistry());
  const snapshotRef = useRef<Map<string, string>>(new Map());
  // Blocks someone else changed while they had unsaved edits here; kept out
  // of saves until the user decides (see markdown/liveMerge.ts).
  const [conflicts, setConflictsState] = useState<ReadonlyMap<string, BlockConflict>>(new Map());
  const conflictsRef = useRef<ReadonlyMap<string, BlockConflict>>(conflicts);
  const setConflicts = useCallback((next: ReadonlyMap<string, BlockConflict>) => {
    conflictsRef.current = next;
    setConflictsState(next);
  }, []);
  // Odd while a save runs; see useLiveNote.
  const saveEpoch = useRef(0);
  // Set while other people's edits are applied, so they don't count as ours.
  const applyingRemote = useRef(false);
  const [noteBody, setNoteBody] = useState<HTMLDivElement | null>(null);
  const [layoutTick, setLayoutTick] = useState(0);
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
    saveEpoch.current += 1;
    try {
      snapshotRef.current = await executeSave(
        notebookId,
        noteId,
        editor,
        registry.current,
        snapshotRef.current,
        new Set(conflictsRef.current.keys()),
      );
    } finally {
      saveEpoch.current += 1;
    }
    // The registry already tracks the new server nodes. Refetching would
    // replace the blocks under the cursor, so only mark the cache stale.
    queryClient.invalidateQueries({
      queryKey: ['nodes', notebookId, noteId],
      refetchType: 'none',
    });
    // The saved note moves to the top of the list with a fresh preview.
    queryClient.invalidateQueries({ queryKey: ['notes', notebookId] });
  }, [notebookId, noteId, editor, queryClient]);

  const autoSave = useAutoSave(save, { enabled: canUpdate });
  const { markDirty, reset: resetAutoSave } = autoSave;

  // --- Title ---
  // The title being typed, or null to show the saved one. The ref is what the
  // save reads, as it may run after newer edits.
  const [titleDraft, setTitleDraft] = useState<string | null>(null);
  const titleDraftRef = useRef<string | null>(null);
  const setDraft = useCallback((draft: string | null) => {
    titleDraftRef.current = draft;
    setTitleDraft(draft);
  }, []);

  const saveTitle = useCallback(async () => {
    const draft = titleDraftRef.current;
    if (!notebookId || !noteId || draft === null) return;
    const updated = await updateNoteTitle(notebookId, noteId, draft.trim());
    queryClient.setQueryData(['note', notebookId, noteId], updated);
    // The saved note moves to the top of the list.
    queryClient.invalidateQueries({ queryKey: ['notes', notebookId] });
    // Show the saved title, unless the user kept typing meanwhile.
    if (titleDraftRef.current === draft) setDraft(null);
  }, [notebookId, noteId, queryClient, setDraft]);

  // The note list follows the title as it is typed.
  const showTitleInList = useCallback(
    (title: string) => {
      queryClient.setQueryData<InfiniteData<Note[]>>(['notes', notebookId], (list) =>
        list && {
          ...list,
          pages: list.pages.map((page) =>
            page.map((item) => (item.id === noteId ? { ...item, title } : item)),
          ),
        },
      );
    },
    [queryClient, notebookId, noteId],
  );

  const titleSave = useAutoSave(saveTitle, { enabled: canUpdate });
  const { markDirty: markTitleDirty, reset: resetTitleSave, flush: flushTitle } = titleSave;

  // Another note: its own title, with nothing pending. The unsaved-changes
  // guard saved the previous one before the route changed.
  useEffect(() => {
    setDraft(null);
    resetTitleSave();
  }, [noteId, setDraft, resetTitleSave]);

  const changeTitle = useCallback(
    (title: string) => {
      if (!canUpdate) return;
      setDraft(title);
      showTitleInList(title);
      markTitleDirty();
    },
    [canUpdate, setDraft, showTitleInList, markTitleDirty],
  );

  const cancelTitle = useCallback(() => {
    setDraft(null);
    resetTitleSave();
    if (note) showTitleInList(note.title);
  }, [setDraft, resetTitleSave, note, showTitleInList]);

  const commitTitle = useCallback(() => {
    void flushTitle();
    const [first] = editor.document;
    if (first) editor.setTextCursorPosition(first, 'start');
    editor.focus();
  }, [flushTitle, editor]);

  // --- Live updates and presence ---
  const isBlockDirty = useCallback(
    (blockId: string) => {
      const block = editor.getBlock(blockId);
      return !!block && editor.blocksToMarkdownLossy([block]).trim() !== snapshotRef.current.get(blockId);
    },
    [editor],
  );

  // Conflicts of blocks the user deleted are over.
  const pruneConflicts = useCallback(() => {
    const current = conflictsRef.current;
    if (current.size === 0) return;
    const ids = new Set(editor.document.map((b) => b.id));
    if ([...current.keys()].every((id) => ids.has(id))) return;
    setConflicts(new Map([...current].filter(([id]) => ids.has(id))));
  }, [editor, setConflicts]);

  const applyRemote = useCallback(
    (run: () => void) => {
      applyingRemote.current = true;
      try {
        run();
      } finally {
        applyingRemote.current = false;
      }
      setLayoutTick((t) => t + 1);
    },
    [],
  );

  const mergeRemoteNodes = useCallback(
    (serverNodes: NoteNode[]) => {
      setAttachmentNodes(serverNodes.filter((n) => n.node_type === 'attachment'));
      const ops = planLiveMerge({
        serverNodes,
        blockIds: editor.document.map((b) => b.id),
        registry: registry.current,
        isDirty: isBlockDirty,
        conflicts: conflictsRef.current,
      });
      if (ops.length === 0) return;
      let next: Map<string, BlockConflict> = new Map();
      applyRemote(() => {
        next = applyLiveMerge(editor, registry.current, snapshotRef.current, conflictsRef.current, ops);
      });
      setConflicts(next);
      // A save stopped by a conflict left other edits unsaved: try again.
      if (ops.some((op) => op.type === 'conflict')) markDirty();
    },
    [editor, isBlockDirty, applyRemote, setConflicts, markDirty],
  );

  const showRemoteTitle = useCallback(
    (title: string) => {
      if (titleDraftRef.current !== null) return;
      queryClient.setQueryData<Note>(['note', notebookId, noteId], (old) => old && { ...old, title });
      showTitleInList(title);
    },
    [queryClient, notebookId, noteId, showTitleInList],
  );

  const live = useLiveNote(notebookId, noteId, {
    saveEpoch,
    onNodes: mergeRemoteNodes,
    onTitle: showRemoteTitle,
  });
  const { pollNow, reset: resetLive } = live;

  const { cursorMoved } = useNotePresence(notebookId, noteId, () =>
    localCursor(editor, registry.current),
  );
  useEffect(() => editor.onSelectionChange(() => cursorMoved()), [editor, cursorMoved]);

  // Someone saved the same block first: merge now, which turns it into a conflict.
  useEffect(() => {
    if (autoSave.error instanceof ApiError && autoSave.error.status === 409) pollNow();
  }, [autoSave.error, pollNow]);

  const keepMine = useCallback(
    (blockId: string) => {
      const conflict = conflictsRef.current.get(blockId);
      if (!conflict) return;
      if (conflict.payload !== null) {
        // Re-apply the local text on top of their version.
        registry.current.updateVersion(blockId, conflict.version);
        snapshotRef.current.set(blockId, conflict.payload);
      }
      // A deleted node: the block is unmapped, so the save creates it again.
      const next = new Map(conflictsRef.current);
      next.delete(blockId);
      setConflicts(next);
      markDirty();
    },
    [setConflicts, markDirty],
  );

  const takeTheirs = useCallback(
    (blockId: string) => {
      const conflict = conflictsRef.current.get(blockId);
      if (!conflict) return;
      applyRemote(() => {
        if (conflict.payload === null) {
          if (editor.document.length === 1) {
            editor.replaceBlocks([blockId], [{ type: 'paragraph', content: [] }]);
          } else {
            editor.removeBlocks([blockId]);
          }
          snapshotRef.current.delete(blockId);
        } else {
          replaceBlockContent(editor, blockId, conflict.payload);
          registry.current.updateVersion(blockId, conflict.version);
          const block = editor.getBlock(blockId);
          if (block) snapshotRef.current.set(blockId, editor.blocksToMarkdownLossy([block]).trim());
        }
      });
      const next = new Map(conflictsRef.current);
      next.delete(blockId);
      setConflicts(next);
    },
    [editor, applyRemote, setConflicts],
  );

  const showBlock = useCallback((blockId: string) => {
    document
      .querySelector<HTMLElement>(`[data-id="${blockId}"]`)
      ?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, []);

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
    setConflicts(new Map());
    resetLive();
    setLayoutTick((t) => t + 1);
  // editor is stable across renders; nodes is the real dependency
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes]);

  // Opened from a search result (`?node=<server node id>`): once the blocks
  // are rendered, scroll to the matching one and flash it, then drop the
  // param so a reload doesn't scroll again. A block that no longer exists
  // just leaves the note open at the top.
  const [searchParams, setSearchParams] = useSearchParams();
  const targetNodeId = searchParams.get('node');
  useEffect(() => {
    if (!nodes || !targetNodeId) return;
    const frame = requestAnimationFrame(() => {
      const blockId = registry.current.blockIdForNode(targetNodeId);
      const element = blockId
        ? document.querySelector<HTMLElement>(`[data-id="${blockId}"]`)
        : null;
      if (element) {
        element.scrollIntoView({ block: 'center', behavior: 'smooth' });
        element.classList.add('search-hit');
        window.setTimeout(() => element.classList.remove('search-hit'), SEARCH_HIT_FLASH_MS);
      }
      setSearchParams(
        (params) => {
          params.delete('node');
          return params;
        },
        { replace: true },
      );
    });
    return () => cancelAnimationFrame(frame);
  }, [nodes, targetNodeId, setSearchParams]);

  // Track changes made by the user
  useEffect(() => {
    const unsubscribe = editor.onChange(() => {
      setDebugTick((t) => t + 1);
      setLayoutTick((t) => t + 1);
      if (applyingRemote.current) return;
      markDirty();
      pruneConflicts();
    });
    return unsubscribe;
  }, [editor, markDirty, pruneConflicts]);

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

  // The popup opens synchronously (popup blockers allow it only inside the
  // click), then loads the note once pending edits are saved. This window
  // goes back to the note list so the note isn't edited in two places.
  const { flush: flushText } = autoSave;
  // A conflict is unsaved text that saving can't settle: the user must decide.
  const flush = useCallback(
    async () =>
      (await flushTitle()) && (await flushText()) && conflictsRef.current.size === 0,
    [flushTitle, flushText],
  );
  const openInNewWindow = useCallback(async () => {
    if (!notebookId || !noteId) return;
    const popup = openNoteWindow(noteId);
    if (!popup) return;
    if (!(await flush())) {
      popup.close();
      return;
    }
    popup.location.href = noteWindowPath(notebookId, noteId);
    popup.focus();
    navigate(`/notebooks/${notebookId}/notes`);
  }, [notebookId, noteId, flush, navigate]);

  const isDirty = autoSave.isDirty || titleSave.isDirty;
  const saving = autoSave.saving || titleSave.saving;
  const hasConflicts = conflicts.size > 0;
  const unsavedChangesDialog = useUnsavedChangesGuard(isDirty || saving || hasConflicts, flush);

  if (!notebookId || !noteId) {
    return <div className="editor-placeholder">Select a note to edit</div>;
  }

  if (isLoading) return <div>Loading...</div>;

  const saveError = autoSave.error;
  const titleError = titleSave.error;
  let errorMessage: string | null = null;
  const savingConflict = saveError instanceof ApiError && saveError.status === 409;
  if (saveError && !savingConflict) {
    errorMessage = `Error: ${saveError instanceof Error ? saveError.message : String(saveError)}`;
  } else if (titleError) {
    const reason = titleError instanceof Error ? titleError.message : String(titleError);
    errorMessage = `Error saving the title: ${reason}`;
  }
  let saveState: string | null = null;
  if (saving) saveState = 'Saving…';
  else if (errorMessage || hasConflicts) saveState = 'Not saved';
  else if (isDirty) saveState = 'Unsaved changes';
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
      <ConflictBar
        conflicts={conflicts}
        onShow={showBlock}
        onKeepMine={keepMine}
        onUseTheirs={takeTheirs}
      />
      {hasConflicts && <style>{conflictStyle(conflicts.keys())}</style>}
      <div className={`editor-content${debugOpen && !isMobile ? ' with-debug' : ''}`}>
        <div className="note-body" ref={setNoteBody}>
          {note && (
            <NoteTitle
              value={titleDraft ?? note.title}
              readOnly={!canUpdate}
              onChange={changeTitle}
              onCommit={commitTitle}
              onCancel={cancelTitle}
              onBlur={() => void flushTitle()}
            />
          )}
          <BlockNoteView
            editor={editor}
            theme={colorScheme}
            portalElements={{ default: null }}
          />
          <RemoteCursors
            editor={editor}
            registry={registry.current}
            users={live.presence}
            container={noteBody}
            layoutKey={layoutTick}
          />
        </div>
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
          <PresenceAvatars users={live.presence} label="Also on this note" />
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
          {!standalone && (
            <button className="open-window-btn" onClick={() => void openInNewWindow()}>
              Open in new window
            </button>
          )}
          {errorMessage && (
            <span className="status error" role="status">{errorMessage}</span>
          )}
        </div>
      )}
      {isMobile && (
        <TopBarActions>
          <PresenceAvatars users={live.presence} label="Also on this note" />
          {saveIndicator}
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
      {unsavedChangesDialog}
    </div>
  );
}
