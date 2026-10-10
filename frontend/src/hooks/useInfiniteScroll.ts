/**
 * Infinite scroll: returns a callback ref for a sentinel element placed at
 * the end of a list. When the sentinel comes within `rootMargin` of the
 * viewport, `onReachEnd` is called.
 *
 * Render the sentinel only while another page can be loaded and none is in
 * flight. Each fetch then unmounts it and the next render mounts a fresh
 * one, whose observer fires right away if the list still doesn't fill the
 * screen, so loading continues until the list overflows.
 */

import { useCallback, useEffect, useRef } from 'react';

export function useInfiniteScroll(
  onReachEnd: () => void,
  rootMargin = '200px',
): (node: Element | null) => void {
  const observerRef = useRef<IntersectionObserver | null>(null);
  const callbackRef = useRef(onReachEnd);

  useEffect(() => {
    callbackRef.current = onReachEnd;
  }, [onReachEnd]);

  useEffect(() => () => observerRef.current?.disconnect(), []);

  return useCallback(
    (node: Element | null) => {
      observerRef.current?.disconnect();
      observerRef.current = null;
      if (!node || typeof IntersectionObserver === 'undefined') return;
      const observer = new IntersectionObserver(
        (entries) => {
          if (entries.some((e) => e.isIntersecting)) callbackRef.current();
        },
        { rootMargin },
      );
      observer.observe(node);
      observerRef.current = observer;
    },
    [rootMargin],
  );
}
