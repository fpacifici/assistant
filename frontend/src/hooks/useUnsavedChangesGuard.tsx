/** Blocks in-app navigation and tab close/reload while there are unsaved changes. */

import { useEffect } from 'react';
import { useBlocker } from 'react-router';
import ConfirmDialog from '../components/ConfirmDialog';

/**
 * While `isDirty`, intercept router navigations that change the pathname
 * (links, back arrow, browser back/swipe) and ask to discard; query-string-only
 * changes pass through. Also registers a `beforeunload` prompt.
 *
 * Returns the confirmation dialog element (or null) for the caller to render.
 * Requires a data router.
 */
export function useUnsavedChangesGuard(isDirty: boolean): React.ReactElement | null {
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      isDirty && currentLocation.pathname !== nextLocation.pathname,
  );

  useEffect(() => {
    if (!isDirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener('beforeunload', onBeforeUnload);
    return () => window.removeEventListener('beforeunload', onBeforeUnload);
  }, [isDirty]);

  if (blocker.state !== 'blocked') return null;

  return (
    <ConfirmDialog
      message="Discard unsaved changes?"
      confirmLabel="Discard"
      cancelLabel="Keep editing"
      onConfirm={() => blocker.proceed()}
      onCancel={() => blocker.reset()}
    />
  );
}
