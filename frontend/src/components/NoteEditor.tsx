import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router';
import { fetchNodes } from '../api/nodes';
import { BlockList } from '../markdown/blockList';
import type { BlockNode } from '../markdown/blockList';
import { parseMarkdownBlocks } from '../markdown/parser';
import { executeSave } from '../markdown/reconcile';
import { useUser } from '../contexts/UserContext';
import DebugBlockView from './DebugBlockView';
import type { DebugBlockSnapshot } from './DebugBlockView';

function lineFromCharOffset(text: string, charOffset: number): number {
  let line = 0;
  for (let i = 0; i < charOffset && i < text.length; i++) {
    if (text[i] === '\n') line++;
  }
  return line;
}

function charOffsetOfBlock(bl: BlockList, target: BlockNode): number {
  let offset = 0;
  let current = bl.head;
  while (current !== null && current !== target) {
    offset += current.content.length + 2; // +2 for \n\n separator
    current = current.next;
  }
  return offset;
}

function charLengthAfterBlock(block: BlockNode): number {
  let length = 0;
  let current = block.next;
  while (current !== null) {
    length += 2 + current.content.length; // +2 for \n\n separator
    current = current.next;
  }
  return length;
}

export default function NoteEditor() {
  const { notebookId, noteId } = useParams();
  const queryClient = useQueryClient();
  const { userId } = useUser();
  const [text, setText] = useState('');
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [debugOpen, setDebugOpen] = useState(false);
  const [debugVersion, setDebugVersion] = useState(0);
  const blockListRef = useRef<BlockList>(new BlockList());
  const currentBlockRef = useRef<BlockNode | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { data: nodes, isLoading } = useQuery({
    queryKey: ['nodes', notebookId, noteId],
    queryFn: () => fetchNodes(notebookId!, noteId!),
    enabled: !!notebookId && !!noteId,
  });

  useEffect(() => {
    if (!nodes || nodes.length === 0) return;

    const bl = blockListRef.current;
    bl.buildFromServerNodes(nodes);
    setText(bl.toText());
    currentBlockRef.current = bl.head;
    setStatus(null);
  }, [nodes]);

  const bumpDebugVersion = useCallback(() => {
    setDebugVersion(v => v + 1);
  }, []);

  const handleTextChange = useCallback((newText: string) => {
    const bl = blockListRef.current;
    const cursorPos = textareaRef.current?.selectionStart ?? 0;
    const cursorLine = lineFromCharOffset(newText, cursorPos);

    const currentBlock = currentBlockRef.current ?? bl.head;
    if (!currentBlock) {
      setText(newText);
      return;
    }

    const blockStart = charOffsetOfBlock(bl, currentBlock);
    const afterLength = charLengthAfterBlock(currentBlock);
    const blockEnd = newText.length - afterLength;
    const blockContent = newText.slice(blockStart, blockEnd);

    const doubleNewlineIdx = blockContent.indexOf('\n\n');
    if (doubleNewlineIdx !== -1) {
      const topContent = blockContent.slice(0, doubleNewlineIdx);
      const bottomContent = blockContent.slice(doubleNewlineIdx + 2);

      bl.updateBlock(currentBlock, topContent);
      const newBlock = bl.insertAfter(currentBlock, 'paragraph', bottomContent);
      bl.updateBlock(newBlock, bottomContent);
      currentBlockRef.current = newBlock;

      const rebuilt = bl.toText();
      setText(rebuilt);
      setStatus(null);
      bumpDebugVersion();
      return;
    }

    const parsed = parseMarkdownBlocks(blockContent);
    if (parsed.length > 1) {
      bl.updateBlock(currentBlock, parsed[0].content);
      let after = currentBlock;
      for (let k = 1; k < parsed.length; k++) {
        after = bl.insertAfter(after, parsed[k].blockType, parsed[k].content);
      }
      currentBlockRef.current = bl.getBlockAtLine(cursorLine);
      setText(bl.toText());
      setStatus(null);
      bumpDebugVersion();
      return;
    }

    // Check for merge: if extracted content is longer than the current block
    // plus the next block, the separator between them was removed
    if (currentBlock.next && blockEnd > blockStart + currentBlock.content.length + 2 + currentBlock.next.content.length) {
      bl.updateBlock(currentBlock, blockContent);
      if (currentBlock.next) {
        bl.remove(currentBlock.next);
      }
      const rebuilt = bl.toText();
      setText(rebuilt);
      currentBlockRef.current = currentBlock;
      setStatus(null);
      bumpDebugVersion();
      return;
    }

    bl.updateBlock(currentBlock, blockContent);

    currentBlockRef.current = bl.getBlockAtLine(cursorLine);
    setText(newText);
    setStatus(null);
    bumpDebugVersion();
  }, [bumpDebugVersion]);

  const handleCursorMove = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const cursorLine = lineFromCharOffset(text, textarea.selectionStart);
    const bl = blockListRef.current;
    currentBlockRef.current = bl.getBlockAtLine(cursorLine);
    bumpDebugVersion();
  }, [text, bumpDebugVersion]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setStatus(null);

    try {
      await executeSave(notebookId!, noteId!, blockListRef.current, userId);
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
  }, [notebookId, noteId, userId, queryClient]);

  const debugBlocks = useMemo((): DebugBlockSnapshot[] => {
    if (!debugOpen) return [];
    const blocks: DebugBlockSnapshot[] = [];
    let current = blockListRef.current.head;
    let index = 0;
    while (current !== null) {
      blocks.push({
        index,
        blockType: current.blockType,
        content: current.content,
        lineStart: current.lineStart,
        lineCount: current.lineCount,
        dirty: current.dirty,
        hasServerState: current.serverState !== null,
        nodeId: current.serverState?.nodeId ?? null,
        version: current.serverState?.version ?? null,
        isCurrent: current === currentBlockRef.current,
      });
      current = current.next;
      index++;
    }
    return blocks;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debugOpen, debugVersion]);

  if (!notebookId || !noteId) {
    return <div className="editor-placeholder">Select a note to edit</div>;
  }

  if (isLoading) return <div>Loading...</div>;

  if (blockListRef.current.head === null && (!nodes || nodes.length === 0)) {
    return <div className="editor-placeholder">No content</div>;
  }

  const isDirty = blockListRef.current.toArray().some(b => b.dirty)
    || blockListRef.current.deletedNodeIds.length > 0;

  return (
    <div className="note-editor">
      <div className={`editor-content${debugOpen ? ' with-debug' : ''}`}>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => handleTextChange(e.target.value)}
          onSelect={handleCursorMove}
          onKeyUp={handleCursorMove}
        />
        {debugOpen && <DebugBlockView blocks={debugBlocks} />}
      </div>
      <div className="editor-toolbar">
        <button
          onClick={handleSave}
          disabled={!isDirty || saving}
        >
          {saving ? 'Saving...' : 'Save'}
        </button>
        <button
          className="debug-toggle"
          onClick={() => setDebugOpen(prev => !prev)}
        >
          {debugOpen ? 'Hide Debug' : 'Debug'}
        </button>
        {status && <span className={`status ${status.startsWith('Error') || status.startsWith('Conflict') ? 'error' : 'success'}`}>{status}</span>}
      </div>
    </div>
  );
}
