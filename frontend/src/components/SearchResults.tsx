/**
 * Results of a note search, shared by the desktop and mobile search page.
 * Each result links to its note, opened at the first matching block; each
 * snippet links to its own block. Highlights come from the API as text
 * segments and are rendered as `<mark>` — never as HTML.
 */

import { useInfiniteQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { searchNotes, SEARCH_PAGE_SIZE } from '../api/search';
import type { SearchResult } from '../types';
import { searchResultUrl } from '../lib/searchResultUrl';
import Highlighted from './Highlighted';
import { NoteTags } from './NoteList';

function SearchResultItem({ result }: { result: SearchResult }) {
  return (
    <li className="search-result">
      <Link to={searchResultUrl(result, result.snippets[0]?.node_id)} className="search-result-title">
        <Highlighted segments={result.title} />
      </Link>
      <div className="search-result-meta">
        <span className="search-result-notebook">{result.notebook.name}</span>
        <NoteTags tags={result.note.tags} />
      </div>
      {result.snippets.map((snippet) => (
        <Link key={snippet.node_id} to={searchResultUrl(result, snippet.node_id)} className="search-snippet">
          <Highlighted segments={snippet.segments} />
        </Link>
      ))}
    </li>
  );
}

export default function SearchResults({ query }: { query: string }) {
  const { data, isPending, isError, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      queryKey: ['search', query],
      queryFn: ({ pageParam }) => searchNotes(query, { offset: pageParam, limit: SEARCH_PAGE_SIZE }),
      initialPageParam: 0,
      getNextPageParam: (lastPage) =>
        lastPage.results.length < lastPage.limit ? undefined : lastPage.offset + lastPage.limit,
    });

  if (isPending) return <p className="search-status">Searching…</p>;
  if (isError) return <p className="search-status auth-error">Search failed. Please try again.</p>;

  const unknownTags = data.pages[0]?.unknown_tags ?? [];
  const results = data.pages.flatMap((p) => p.results);

  if (unknownTags.length > 0) {
    return (
      <p className="search-status">
        {unknownTags.map((tag) => `You have no tag “${tag}”.`).join(' ')}
      </p>
    );
  }
  if (results.length === 0) return <p className="search-status">No notes match your search.</p>;

  return (
    <>
      <ul className="search-results">
        {results.map((result) => (
          <SearchResultItem key={result.note.id} result={result} />
        ))}
      </ul>
      {hasNextPage && (
        <button
          type="button"
          className="btn-secondary search-more"
          onClick={() => fetchNextPage()}
          disabled={isFetchingNextPage}
        >
          {isFetchingNextPage ? 'Loading…' : 'Load more'}
        </button>
      )}
    </>
  );
}
