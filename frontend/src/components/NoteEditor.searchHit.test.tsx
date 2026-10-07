/**
 * Opening a note from a search result (`?node=<server node id>`) scrolls to
 * that block and flashes it. BlockNote is mocked to render one element per
 * block with `data-id`, as the real editor does.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router';
import NoteEditor from './NoteEditor';
import { renderWithProviders } from '../test/renderWithProviders';
import type { BlockNoteEditor } from '@blocknote/core';
import type { NoteNode } from '../types';

vi.mock('../api/notes', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/notes')>()),
  fetchNote: vi.fn().mockResolvedValue({
    id: 'note-1',
    notebook_id: 'nb-1',
    owner_id: 'u1',
    title: 'Trip',
    creation_timestamp: '',
    update_timestamp: '',
    permissions: ['view_note'],
    tags: [],
  }),
}));
vi.mock('../api/nodes', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../api/nodes')>()),
  fetchNodes: vi.fn(),
}));
vi.mock('../api/tags', () => ({
  fetchTags: vi.fn().mockResolvedValue([]),
  addNoteTag: vi.fn(),
  removeNoteTag: vi.fn(),
}));
vi.mock('../markdown/reconcile', () => ({ executeSave: vi.fn() }));

let renderedBlockIds: string[] = [];
let rerenderView: (() => void) | undefined;

vi.mock('@blocknote/react', () => ({
  useCreateBlockNote: () =>
    ({
      isEditable: false,
      document: [],
      // One block per payload, with an id distinct from the server node id.
      tryParseMarkdownToBlocks: (payload: string) => [{ id: `block-${payload}` }],
      replaceBlocks: (_old: unknown, blocks: { id: string }[]) => {
        renderedBlockIds = blocks.map((b) => b.id);
        rerenderView?.();
      },
      blocksToMarkdownLossy: () => '',
      onChange: () => () => {},
    }) as unknown as BlockNoteEditor,
}));

vi.mock('@blocknote/mantine', async () => {
  const { useReducer } = await import('react');
  return {
    BlockNoteView: () => {
      const [, force] = useReducer((n: number) => n + 1, 0);
      rerenderView = force;
      return (
        <div data-testid="blocknote-view">
          {renderedBlockIds.map((id) => (
            <div key={id} data-id={id} data-testid={id} />
          ))}
        </div>
      );
    },
  };
});

import { fetchNodes } from '../api/nodes';
const mockFetchNodes = vi.mocked(fetchNodes);

function node(id: string, payload: string): NoteNode {
  return {
    id,
    note_id: 'note-1',
    author_id: 'u1',
    node_type: 'markdown',
    payload,
    block_type: 'paragraph',
    version: 1,
    update_timestamp: '',
  };
}

function renderAt(url: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/notebooks/:notebookId/notes/:noteId" element={<NoteEditor />} />
    </Routes>,
    { initialEntries: [url] },
  );
}

describe('NoteEditor opened from a search result', () => {
  const scrollIntoView = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    renderedBlockIds = [];
    Element.prototype.scrollIntoView = scrollIntoView;
    mockFetchNodes.mockResolvedValue([node('n1', 'Groceries'), node('n2', 'Berlin')]);
  });

  it('scrolls to and flashes the matching block, then drops the param', async () => {
    const { router } = renderAt('/notebooks/nb-1/notes/note-1?node=n2');

    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1));
    expect(scrollIntoView.mock.contexts[0]).toBe(screen.getByTestId('block-Berlin'));
    expect(screen.getByTestId('block-Berlin')).toHaveClass('search-hit');
    expect(screen.getByTestId('block-Groceries')).not.toHaveClass('search-hit');
    await waitFor(() => expect(router.state.location.search).toBe(''));
    expect(router.state.location.pathname).toBe('/notebooks/nb-1/notes/note-1');
  });

  it('opens at the top when the block no longer exists', async () => {
    const { router } = renderAt('/notebooks/nb-1/notes/note-1?node=gone');

    await waitFor(() => expect(router.state.location.search).toBe(''));
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('does not scroll without a node param', async () => {
    renderAt('/notebooks/nb-1/notes/note-1');

    await screen.findByTestId('block-Berlin');
    expect(scrollIntoView).not.toHaveBeenCalled();
  });
});
