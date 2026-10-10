/** Keeps the session alive while the page is visible. */

import { useEffect } from 'react';
import { refreshSession } from '../api/auth';

/** Below the backend's 5-minute access-token lifetime. */
export const HEARTBEAT_INTERVAL_MS = 4 * 60 * 1000;

/**
 * While `enabled`, refresh the session cookies every `HEARTBEAT_INTERVAL_MS`
 * as long as the page is visible, and right away when a hidden page becomes
 * visible again after a full interval. Failures are ignored: the next beat
 * retries, and an expired session surfaces on the next API call.
 */
export function useSessionHeartbeat(enabled: boolean): void {
  useEffect(() => {
    if (!enabled) return;
    let lastBeat = Date.now();

    const beat = () => {
      lastBeat = Date.now();
      refreshSession().catch(() => {});
    };

    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') beat();
    }, HEARTBEAT_INTERVAL_MS);

    const onVisibilityChange = () => {
      if (
        document.visibilityState === 'visible' &&
        Date.now() - lastBeat >= HEARTBEAT_INTERVAL_MS
      ) {
        beat();
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [enabled]);
}
