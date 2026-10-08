/** Blocks in-app navigation and tab close/reload while there are unsaved changes. */

import { useEffect, useRef, useState } from 'react';
import { useBlocker } from 'react-router';
import ConfirmDialog from '../components/ConfirmDialog';

/**
 * While `isDirty`, intercept router navigations that change the pathname
 * (links, back arrow, browser back/swipe) and ask to discard; query-string-only
 * changes pass through. Also registers a `beforeunload` prompt.
 *
 * With `flush`, a blocked navigation first tries to save: it proceeds when
 * `flush` resolves true and only asks to discard if saving failed.
 *
 * Returns the confirmation dialog element (or null) for the caller to render.
 * Requires a data router.
 */
export function useUnsavedChangesGuard(
  isDirty: boolean,
  flush?: () => Promise<boolean>,
): React.ReactElement | null {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty && currentLocation.pathname !== nextLocation.pathname,
  );
  // The blocked navigation whose flush failed; ask the user about that one.
  const [failedLocation, setFailedLocation] = useState<string | null>(null);
  const flushing = useRef(false);
  const blockedKey = blocker.state === 'blocked' ? blocker.location.key : null;

  useEffect(() => {
    if (blocker.state !== 'blocked' || !flush || flushing.current) return;
    if (failedLocation === blocker.location.key) return;
    flushing.current = true;
    const key = blocker.location.key;
    void flush().then((ok) => {
      flushing.current = false;
      if (ok) blocker.proceed();
      else setFailedLocation(key);
    });
  // blockedKey identifies the blocked navigation; blocker changes every render
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blockedKey, flush, failedLocation]);

  useEffect(() => {
    if (!isDirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [isDirty]);

  if (blocker.state !== 'blocked') return null;
  if (flush && failedLocation !== blocker.location.key) return null;

  return (
    <ConfirmDialog
      message="Discard unsaved changes?"
      confirmLabel="Discard"
      cancelLabel="Keep editing"
      onConfirm={() => {
        setFailedLocation(null);
        blocker.proceed();
      }}
      onCancel={() => {
        setFailedLocation(null);
        blocker.reset();
      }}
    />
  );
}
