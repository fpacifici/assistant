import { it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useAutoSave } from './useAutoSave';

const DELAY = 1000;

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

it('keeps edits made during a save dirty and saves them next', async () => {
  const first = deferred();
  const save = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(undefined);
  const { result } = renderHook(() => useAutoSave(save, { delayMs: DELAY }));

  act(() => result.current.markDirty());
  await act(() => vi.advanceTimersByTimeAsync(DELAY));
  expect(save).toHaveBeenCalledTimes(1);
  expect(result.current.saving).toBe(true);

  act(() => result.current.markDirty());
  await act(async () => first.resolve());
  expect(result.current.isDirty).toBe(true);

  await act(() => vi.advanceTimersByTimeAsync(DELAY));
  expect(save).toHaveBeenCalledTimes(2);
  expect(result.current.isDirty).toBe(false);
});

it('flush saves immediately and waits for an in-flight save', async () => {
  const first = deferred();
  const save = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(undefined);
  const { result } = renderHook(() => useAutoSave(save, { delayMs: DELAY }));

  act(() => result.current.markDirty());
  await act(() => vi.advanceTimersByTimeAsync(DELAY));
  act(() => result.current.markDirty());

  let flushed: Promise<boolean> = Promise.resolve(false);
  act(() => {
    flushed = result.current.flush();
  });
  await act(async () => first.resolve());

  await expect(flushed).resolves.toBe(true);
  expect(save).toHaveBeenCalledTimes(2);
  expect(result.current.isDirty).toBe(false);
});

it('flush reports failure and keeps the edits dirty', async () => {
  const save = vi.fn().mockRejectedValue(new Error('boom'));
  const { result } = renderHook(() => useAutoSave(save, { delayMs: DELAY }));

  act(() => result.current.markDirty());
  let ok = true;
  await act(async () => {
    ok = await result.current.flush();
  });

  expect(ok).toBe(false);
  expect(result.current.isDirty).toBe(true);
  expect(result.current.error).toEqual(new Error('boom'));
});

it('does not schedule saves while disabled', async () => {
  const save = vi.fn().mockResolvedValue(undefined);
  const { result } = renderHook(() => useAutoSave(save, { enabled: false, delayMs: DELAY }));

  act(() => result.current.markDirty());
  await act(() => vi.advanceTimersByTimeAsync(DELAY * 2));

  expect(save).not.toHaveBeenCalled();
  expect(result.current.isDirty).toBe(true);
});

it('reset drops pending edits and the timer', async () => {
  const save = vi.fn().mockResolvedValue(undefined);
  const { result } = renderHook(() => useAutoSave(save, { delayMs: DELAY }));

  act(() => result.current.markDirty());
  act(() => result.current.reset());
  await act(() => vi.advanceTimersByTimeAsync(DELAY * 2));

  expect(save).not.toHaveBeenCalled();
  expect(result.current.isDirty).toBe(false);
});
