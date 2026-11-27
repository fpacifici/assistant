import { it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { CURSOR_THROTTLE_MS, HEARTBEAT_MS, useNotePresence } from './useNotePresence';
import type { PresenceCursor } from '../types';

vi.mock('../api/presence', () => ({ sendHeartbeat: vi.fn(), leaveNote: vi.fn() }));

import { leaveNote, sendHeartbeat } from '../api/presence';

const mockBeat = vi.mocked(sendHeartbeat);
const mockLeave = vi.mocked(leaveNote);
let visibility: DocumentVisibilityState = 'visible';
let cursor: PresenceCursor | null = null;

function setVisibility(state: DocumentVisibilityState) {
  visibility = state;
  document.dispatchEvent(new Event('visibilitychange'));
}

function render(noteId = 'note-1') {
  return renderHook(({ id }) => useNotePresence('nb-1', id, () => cursor), {
    initialProps: { id: noteId },
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  mockBeat.mockResolvedValue(undefined);
  visibility = 'visible';
  cursor = null;
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

// --- Heartbeat ---

it('beats when the note opens and every interval with the cursor', () => {
  render();
  expect(mockBeat).toHaveBeenCalledTimes(1);
  const clientId = mockBeat.mock.calls[0][2];

  cursor = { node_id: 'n1', offset: 3 };
  act(() => vi.advanceTimersByTime(HEARTBEAT_MS));

  expect(mockBeat).toHaveBeenCalledTimes(2);
  expect(mockBeat).toHaveBeenLastCalledWith('nb-1', 'note-1', clientId, cursor);
});

it('does not beat while the page is hidden, and beats when it shows again', () => {
  render();
  setVisibility('hidden');
  act(() => vi.advanceTimersByTime(HEARTBEAT_MS * 3));
  expect(mockBeat).toHaveBeenCalledTimes(1);

  setVisibility('visible');
  expect(mockBeat).toHaveBeenCalledTimes(2);
});

// --- Cursor ---

it('sends cursor moves at most once per throttle window', () => {
  const { result } = render();
  act(() => vi.advanceTimersByTime(CURSOR_THROTTLE_MS));

  act(() => result.current.cursorMoved());
  expect(mockBeat).toHaveBeenCalledTimes(2);

  act(() => result.current.cursorMoved());
  act(() => result.current.cursorMoved());
  expect(mockBeat).toHaveBeenCalledTimes(2);

  act(() => vi.advanceTimersByTime(CURSOR_THROTTLE_MS));
  expect(mockBeat).toHaveBeenCalledTimes(3);
});

// --- Leave ---

it('leaves the note on unmount and when switching notes', () => {
  const { rerender, unmount } = render();
  const clientId = mockBeat.mock.calls[0][2];

  rerender({ id: 'note-2' });
  expect(mockLeave).toHaveBeenCalledWith('nb-1', 'note-1', clientId);
  expect(mockBeat).toHaveBeenLastCalledWith('nb-1', 'note-2', clientId, null);

  unmount();
  expect(mockLeave).toHaveBeenLastCalledWith('nb-1', 'note-2', clientId);
});

it('leaves the note when the page goes away', () => {
  render();
  window.dispatchEvent(new Event('pagehide'));
  expect(mockLeave).toHaveBeenCalledTimes(1);
});

it('does nothing without a note', () => {
  renderHook(() => useNotePresence('nb-1', undefined, () => null));
  act(() => vi.advanceTimersByTime(HEARTBEAT_MS));
  expect(mockBeat).not.toHaveBeenCalled();
});
