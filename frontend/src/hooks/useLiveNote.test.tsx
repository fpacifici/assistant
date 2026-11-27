import { it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useLiveNote } from './useLiveNote';
import type { LiveNote, NoteNode } from '../types';

vi.mock('../api/presence', () => ({ fetchLiveNote: vi.fn() }));

import { fetchLiveNote } from '../api/presence';

const mockFetch = vi.mocked(fetchLiveNote);

const NODE: NoteNode = {
  id: 'n1',
  note_id: 'note-1',
  author_id: 'u1',
  node_type: 'markdown',
  payload: 'hi',
  block_type: 'paragraph',
  version: 1,
  update_timestamp: '',
};

function live(overrides: Partial<LiveNote> = {}): LiveNote {
  return { revision: 'r1', title: 'Title', nodes: [NODE], presence: [], ...overrides };
}

function render(saveEpoch = { current: 0 }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const onNodes = vi.fn();
  const onTitle = vi.fn();
  const hook = renderHook(
    () => useLiveNote('nb-1', 'note-1', { saveEpoch, onNodes, onTitle }),
    { wrapper },
  );
  return { ...hook, onNodes, onTitle, saveEpoch };
}

beforeEach(() => {
  vi.clearAllMocks();
});

// --- Nodes ---

it('merges the nodes, then asks from the merged revision', async () => {
  mockFetch.mockResolvedValueOnce(live()).mockResolvedValue(live({ nodes: null }));
  const { result, onNodes } = render();

  await waitFor(() => expect(onNodes).toHaveBeenCalledWith([NODE]));
  expect(mockFetch).toHaveBeenLastCalledWith('nb-1', 'note-1', null);

  result.current.pollNow();
  await waitFor(() => expect(mockFetch).toHaveBeenLastCalledWith('nb-1', 'note-1', 'r1'));
  expect(onNodes).toHaveBeenCalledTimes(1);
});

it('drops nodes fetched while a save runs and asks for them again', async () => {
  const saveEpoch = { current: 1 }; // a save is running
  mockFetch.mockResolvedValue(live());
  const { result, onNodes } = render(saveEpoch);

  await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
  expect(onNodes).not.toHaveBeenCalled();

  saveEpoch.current = 2; // saved
  result.current.pollNow();
  await waitFor(() => expect(onNodes).toHaveBeenCalledTimes(1));
  expect(mockFetch).toHaveBeenLastCalledWith('nb-1', 'note-1', null);
});

it('drops nodes when a save started after the request was sent', async () => {
  const saveEpoch = { current: 0 };
  let answer: (value: LiveNote) => void = () => {};
  mockFetch.mockImplementationOnce(() => new Promise((resolve) => (answer = resolve)));
  const { onNodes } = render(saveEpoch);
  await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));

  saveEpoch.current = 2; // a whole save ran meanwhile
  answer(live());

  await waitFor(() => expect(mockFetch).toHaveBeenCalledTimes(1));
  expect(onNodes).not.toHaveBeenCalled();
});

// --- Title and presence ---

it('reports a title changed after the first poll', async () => {
  mockFetch
    .mockResolvedValueOnce(live())
    .mockResolvedValue(live({ nodes: null, revision: 'r2', title: 'Renamed' }));
  const { result, onNodes, onTitle } = render();
  await waitFor(() => expect(onNodes).toHaveBeenCalledTimes(1));
  expect(onTitle).not.toHaveBeenCalled();

  result.current.pollNow();
  await waitFor(() => expect(onTitle).toHaveBeenCalledWith('Renamed'));
});

it('returns who else is on the note', async () => {
  const bob = { user_id: 'u2', name: 'Bob', initial: 'B', cursor: null };
  mockFetch.mockResolvedValue(live({ presence: [bob] }));
  const { result } = render();

  await waitFor(() => expect(result.current.presence).toEqual([bob]));
});
