import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { HEARTBEAT_INTERVAL_MS, useSessionHeartbeat } from './useSessionHeartbeat';

vi.mock('../api/auth', () => ({ refreshSession: vi.fn() }));

import { refreshSession } from '../api/auth';

const mockRefresh = vi.mocked(refreshSession);
let visibility: DocumentVisibilityState = 'visible';

function setVisibility(state: DocumentVisibilityState) {
  visibility = state;
  document.dispatchEvent(new Event('visibilitychange'));
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  mockRefresh.mockResolvedValue({} as Awaited<ReturnType<typeof refreshSession>>);
  visibility = 'visible';
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
});

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
});

it('refreshes the session every interval while visible', () => {
  renderHook(() => useSessionHeartbeat(true));

  act(() => vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS - 1));
  expect(mockRefresh).not.toHaveBeenCalled();
  act(() => vi.advanceTimersByTime(1));
  expect(mockRefresh).toHaveBeenCalledTimes(1);
  act(() => vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS));
  expect(mockRefresh).toHaveBeenCalledTimes(2);
});

describe('while hidden', () => {
  it('skips beats and refreshes as soon as the page is visible again', () => {
    renderHook(() => useSessionHeartbeat(true));
    setVisibility('hidden');

    act(() => vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS * 2));
    expect(mockRefresh).not.toHaveBeenCalled();

    setVisibility('visible');
    expect(mockRefresh).toHaveBeenCalledTimes(1);
  });

  it('does not refresh on a quick tab switch', () => {
    renderHook(() => useSessionHeartbeat(true));
    setVisibility('hidden');
    act(() => vi.advanceTimersByTime(1000));
    setVisibility('visible');

    expect(mockRefresh).not.toHaveBeenCalled();
  });
});

it('ignores refresh failures', () => {
  mockRefresh.mockRejectedValue(new Error('401'));
  renderHook(() => useSessionHeartbeat(true));

  act(() => vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS * 2));
  expect(mockRefresh).toHaveBeenCalledTimes(2);
});

it('does nothing when disabled', () => {
  renderHook(() => useSessionHeartbeat(false));

  act(() => vi.advanceTimersByTime(HEARTBEAT_INTERVAL_MS * 2));
  expect(mockRefresh).not.toHaveBeenCalled();
});
