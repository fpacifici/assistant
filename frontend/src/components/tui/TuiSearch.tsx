/**
 * Search window of the TUI layout (`/`, or File → Search notes…), in the
 * spirit of mc's Find File: a `Find:` line over a framed result list.
 *
 * Results follow the query as you type (debounced, so the last word matches
 * as a prefix). Focus stays in the query field: ↑/↓/PgUp/PgDn move the
 * cursor, Enter opens the note at its best matching block, Esc closes.
 */

import { useEffect, useState } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { searchNotes, SEARCH_PAGE_SIZE } from '../../api/search';
import type { SearchResult } from '../../types';
import Highlighted from '../Highlighted';
import TuiBorder from './TuiBorder';
import TuiList from './TuiList';
import { useListCursor } from './listCursor';

/** Delay after the last keystroke before searching. */
export const SEARCH_DEBOUNCE_MS = 250;

const CURSOR_KEYS = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  PageUp: 'pageUp',
  PageDown: 'pageDown',
} as const;

function useDebounced(value: string, delayMs: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

interface Row {
  id: string;
  result: SearchResult;
}

function ResultRow({ result }: { result: SearchResult }) {
  const snippet = result.snippets[0];
  return (
    <>
      <span className="tui-row-line">
        <span className="tui-row-title">
          <Highlighted segments={result.title} />
        </span>
        <span className="tui-row-sub">
          {'  '}
          {result.notebook.name}
          {result.note.tags.map((tag) => (
            <span key={tag.id} className="tui-tag"> #{tag.name}</span>
          ))}
        </span>
      </span>
      {snippet && (
        <span className="tui-row-line tui-row-sub">
          <Highlighted segments={snippet.segments} />
        </span>
      )}
    </>
  );
}

export default function TuiSearch({
  initialQuery,
  onQueryChange,
  onOpen,
  onClose,
}: {
  initialQuery: string;
  /** Called on every edit, so the window can reopen with the same query. */
  onQueryChange: (query: string) => void;
  onOpen: (result: SearchResult) => void;
  onClose: () => void;
}) {
  const [query, setQuery] = useState(initialQuery);
  const debounced = useDebounced(query, SEARCH_DEBOUNCE_MS);
  // The raw query (not trimmed): a trailing space ends prefix matching.
  const active = debounced.trim() ? debounced : '';

  const { data, isFetching, isError, fetchNextPage, hasNextPage } = useInfiniteQuery({
    queryKey: ['search', active],
    queryFn: ({ pageParam }) => searchNotes(active, { offset: pageParam, limit: SEARCH_PAGE_SIZE }),
    initialPageParam: 0,
    getNextPageParam: (lastPage) =>
      lastPage.results.length < lastPage.limit ? undefined : lastPage.offset + lastPage.limit,
    enabled: !!active,
  });

  const rows: Row[] = (data?.pages ?? []).flatMap((p) =>
    p.results.map((result) => ({ id: result.note.id, result })),
  );
  const unknownTags = data?.pages[0]?.unknown_tags ?? [];
  const cursor = useListCursor(rows, undefined, () => {
    if (hasNextPage) void fetchNextPage();
  });

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key in CURSOR_KEYS) {
      cursor.move(CURSOR_KEYS[e.key as keyof typeof CURSOR_KEYS]);
    } else if (e.key === 'Enter') {
      if (cursor.current) onOpen(cursor.current.result);
    } else if (e.key === 'Escape') {
      onClose();
    } else {
      return;
    }
    e.preventDefault();
  };

  let status: string;
  if (!active) status = 'Words, "exact phrases", tag:name';
  else if (isError) status = 'Search failed';
  else if (unknownTags.length > 0) status = unknownTags.map((t) => `You have no tag “${t}”.`).join(' ');
  else if (!data && isFetching) status = 'Searching…';
  else status = `${rows.length}${hasNextPage ? '+' : ''} found`;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal tui-dialog tui-search tui-framed"
        role="dialog"
        aria-modal="true"
        aria-label="Search"
        onClick={(e) => e.stopPropagation()}
      >
        <TuiBorder title="Search" footer="↑↓ move · Enter open · Esc close" active />
        <label className="tui-field">
          <span>Find:</span>
          <input
            autoFocus
            aria-label="Find"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              onQueryChange(e.target.value);
            }}
            onKeyDown={onKeyDown}
          />
        </label>
        <p className="tui-search-status" role="status">{status}</p>
        {active && unknownTags.length === 0 && (
          <TuiList
            label="Search results"
            items={rows}
            cursorIndex={cursor.index}
            emptyText={data ? 'No notes match.' : ''}
            onActivate={(row) => onOpen(row.result)}
            renderRow={(row) => <ResultRow result={row.result} />}
          />
        )}
      </div>
    </div>
  );
}
