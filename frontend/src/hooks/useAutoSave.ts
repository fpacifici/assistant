/** Batches edits and saves them automatically after a fixed delay. */

import { useCallback, useEffect, useRef, useState } from 'react';

const DEFAULT_AUTOSAVE_SECONDS = 5;

function readAutosaveDelayMs(): number {
  const seconds = Number(import.meta.env.VITE_AUTOSAVE_SECONDS);
  return (Number.isFinite(seconds) && seconds > 0 ? seconds : DEFAULT_AUTOSAVE_SECONDS) * 1000;
}

/** Delay between the first unsaved edit and the save; `VITE_AUTOSAVE_SECONDS` (default 5). */
export const AUTOSAVE_DELAY_MS = readAutosaveDelayMs();

export interface AutoSave {
  /** True while some edits have not been persisted. */
  isDirty: boolean;
  saving: boolean;
  /** Error from the last save attempt; cleared by the next successful save. */
  error: unknown;
  /** Record an edit. Starts the save timer unless one is already pending. */
  markDirty: () => void;
  /** Save pending edits now. Resolves true once nothing is left unsaved. */
  flush: () => Promise<boolean>;
  /** Forget pending edits and errors (e.g. after loading fresh content). */
  reset: () => void;
}

/**
 * Accumulates edits for `delayMs` after the first one, then calls `save` if
 * anything changed. Edits made while a save is in flight stay dirty and
 * schedule the next save. A failed save keeps the edits dirty; the next edit
 * (or `flush`) retries. While `enabled` is false no save is scheduled.
 */
export function useAutoSave(
  save: () => Promise<void>,
  { enabled = true, delayMs = AUTOSAVE_DELAY_MS }: { enabled?: boolean; delayMs?: number } = {},
): AutoSave {
  const [isDirty, setIsDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  // Edits are numbered so a save only clears the edits it actually sent.
  const changeSeq = useRef(0);
  const savedSeq = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inFlight = useRef<Promise<boolean> | null>(null);
  const saveRef = useRef(save);
  const enabledRef = useRef(enabled);
  const delayRef = useRef(delayMs);
  // Bumped by reset() so a save started before it does not touch the new state.
  const generation = useRef(0);

  useEffect(() => {
    saveRef.current = save;
    enabledRef.current = enabled;
    delayRef.current = delayMs;
  });

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  // Created once; they only read refs.
  const [{ runSave, schedule }] = useState(() => {
    const scheduleFn = () => {
      if (timer.current === null && !inFlight.current) {
        timer.current = setTimeout(() => {
          timer.current = null;
          void runSaveFn();
        }, delayRef.current);
      }
    };

    // Resolves true when the save succeeded (newer edits may still be pending).
    const runSaveFn = (): Promise<boolean> => {
      clearTimer();
      if (inFlight.current) return inFlight.current;
      if (changeSeq.current === savedSeq.current) return Promise.resolve(true);

      const gen = generation.current;
      const seq = changeSeq.current;
      setSaving(true);
      const promise = (async () => {
        let ok = false;
        try {
          await saveRef.current();
          ok = true;
        } catch (err) {
          if (gen === generation.current) setError(err);
        }
        if (gen !== generation.current) return ok;
        inFlight.current = null;
        setSaving(false);
        if (!ok) return false;
        savedSeq.current = seq;
        setError(null);
        const dirty = changeSeq.current !== savedSeq.current;
        setIsDirty(dirty);
        if (dirty && enabledRef.current) scheduleFn();
        return true;
      })();
      inFlight.current = promise;
      return promise;
    };

    return { runSave: runSaveFn, schedule: scheduleFn };
  });

  const markDirty = useCallback(() => {
    changeSeq.current += 1;
    setIsDirty(true);
    if (enabledRef.current) schedule();
  }, [schedule]);

  const flush = useCallback(async () => {
    // A save in flight may not include the latest edits; save again if needed.
    while (changeSeq.current !== savedSeq.current) {
      if (!(await runSave())) return false;
    }
    return true;
  }, [runSave]);

  const reset = useCallback(() => {
    clearTimer();
    generation.current += 1;
    inFlight.current = null;
    changeSeq.current = 0;
    savedSeq.current = 0;
    setIsDirty(false);
    setSaving(false);
    setError(null);
  }, [clearTimer]);

  useEffect(() => clearTimer, [clearTimer]);

  return { isDirty, saving, error, markDirty, flush, reset };
}
