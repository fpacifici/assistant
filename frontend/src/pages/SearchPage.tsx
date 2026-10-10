/**
 * Note search (`/search?q=…`). The query lives in the URL so results can be
 * shared and the back button works.
 *
 * Desktop: the app header (whose search box shows the query) above the
 * results. Mobile: a full-screen view with its own focused search input.
 */

import { useSearchParams } from 'react-router';
import { useLayoutMode } from '../layout/LayoutModeContext';
import DesktopHeader from '../components/DesktopHeader';
import MobileTopBar from '../components/MobileTopBar';
import SearchBox from '../components/SearchBox';
import SearchResults from '../components/SearchResults';

function SearchHelp() {
  return (
    <p className="search-status">
      Search your notes by words, <code>"exact phrases"</code> and tags with{' '}
      <code>tag:name</code> (or <code>tag:"two words"</code>).
    </p>
  );
}

export default function SearchPage() {
  const mode = useLayoutMode();
  const isMobile = mode === 'mobile';
  const [searchParams] = useSearchParams();
  const query = searchParams.get('q')?.trim() ?? '';

  return (
    <div className="app-shell" data-layout={mode}>
      {isMobile ? (
        <>
          <MobileTopBar title="Search" backTo="/notebooks" hideSearch />
          <div className="search-page-input">
            <SearchBox key={query} initialQuery={query} autoFocus />
          </div>
        </>
      ) : (
        <DesktopHeader />
      )}
      <main className="search-page">
        {query ? <SearchResults query={query} /> : <SearchHelp />}
      </main>
    </div>
  );
}
