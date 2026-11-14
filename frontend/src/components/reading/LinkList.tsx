/**
 * The links of one state, optionally narrowed to a category or Unfiled,
 * paged by the server's keyset cursor.
 *
 * While any link on screen is being analyzed the list polls, for at most
 * `MAX_POLL_MS` after the last change and never when AI is off (nothing
 * analyzes links then). When an analysis finishes, every Reading query is
 * refreshed: the link may now belong to another category section, and the
 * counts change.
 */

import { useEffect, useRef } from 'react';
import { useInfiniteQuery, useQueryClient } from '@tanstack/react-query';
import { fetchLinks, READING_KEY } from '../../api/reading';
import { useAskEnabled } from '../../hooks/useAskEnabled';
import type { LinkFilter } from '../../api/reading';
import type { Category, LinkState, ReadingLink } from '../../types';
import LinkCard from './LinkCard';

/** How often a list with links being analyzed asks again. */
export const PENDING_POLL_MS = 3000;
/** Polling stops when nothing changed for this long; a reload starts it again. */
export const MAX_POLL_MS = 5 * 60 * 1000;

interface LinkListProps {
  state: LinkState;
  filter: LinkFilter;
  categories: Category[];
  emptyText: string;
  onPromote: (link: ReadingLink) => void;
}

export default function LinkList({
  state,
  filter,
  categories,
  emptyText,
  onPromote,
}: LinkListProps) {
  const queryClient = useQueryClient();
  const aiEnabled = useAskEnabled();
  // When the set of pending links last changed.
  const pendingSince = useRef(Date.now());
  const { data, isPending, isError, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      queryKey: [...READING_KEY, 'links', state, filter],
      queryFn: ({ pageParam }) => fetchLinks(state, filter, pageParam),
      initialPageParam: undefined as string | undefined,
      getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
      refetchInterval: (query) =>
        aiEnabled &&
        Date.now() - pendingSince.current < MAX_POLL_MS &&
        query.state.data?.pages.some((page) =>
          page.links.some((link) => link.analysis_status === 'pending'),
        )
          ? PENDING_POLL_MS
          : false,
    });

  const links = data?.pages.flatMap((page) => page.links) ?? [];
  const pendingIds = links
    .filter((link) => link.analysis_status === 'pending')
    .map((link) => link.id);
  const pendingKey = pendingIds.join(',');

  // Refresh everything once a link that was being analyzed is done.
  const wasPending = useRef<Set<string>>(new Set());
  useEffect(() => {
    const now = new Set(pendingKey ? pendingKey.split(',') : []);
    const finished = [...wasPending.current].some((id) => !now.has(id));
    const changed = finished || [...now].some((id) => !wasPending.current.has(id));
    if (changed) pendingSince.current = Date.now();
    wasPending.current = now;
    if (finished) void queryClient.invalidateQueries({ queryKey: [...READING_KEY] });
  }, [pendingKey, queryClient]);

  if (isPending) return <p className="search-status">Loading…</p>;
  if (isError) return <p className="search-status auth-error">Could not load the links.</p>;
  if (links.length === 0) return <p className="search-status">{emptyText}</p>;

  return (
    <>
      <ul className="blog-posts">
        {links.map((link) => (
          <LinkCard key={link.id} link={link} categories={categories} onPromote={onPromote} />
        ))}
      </ul>
      {hasNextPage && (
        <button
          type="button"
          className="btn-secondary link-more"
          disabled={isFetchingNextPage}
          onClick={() => void fetchNextPage()}
        >
          {isFetchingNextPage ? 'Loading…' : 'Show more'}
        </button>
      )}
    </>
  );
}
