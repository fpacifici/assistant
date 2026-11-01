/**
 * Blog posts: All (`/blogs`), Relevant (`/blogs/relevant`) and New
 * (`/blogs/review`). The filters live in the URL: `?directory=` (an id,
 * `unfiled` or `all`), `?source=` (an archived source) and `?tag=`.
 *
 * Desktop: the app header above a directory sidebar and the posts. Mobile: one
 * level at a time, the directories, then the posts of the chosen one. TUI mode
 * shows the desktop page.
 */

import { Link, useLocation, useSearchParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import type { PostFilters } from '../api/blogs';
import { fetchTags } from '../api/tags';
import BlogDirectoryList, {
  ALL_DIRECTORIES,
  UNFILED,
} from '../components/blogs/BlogDirectoryList';
import PostList from '../components/blogs/PostList';
import DesktopHeader from '../components/DesktopHeader';
import MobileTopBar from '../components/MobileTopBar';
import { useLayoutMode } from '../layout/LayoutModeContext';
import type { PostView } from '../types';

const TABS: { view: PostView; to: string; label: string }[] = [
  { view: 'all', to: '/blogs', label: 'All' },
  { view: 'relevant', to: '/blogs/relevant', label: 'Relevant' },
  { view: 'new', to: '/blogs/review', label: 'New' },
];

function TagFilter() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: tags = [] } = useQuery({ queryKey: ['tags'], queryFn: fetchTags });

  const choose = (tagId: string) => {
    const next = new URLSearchParams(searchParams);
    if (tagId) next.set('tag', tagId);
    else next.delete('tag');
    setSearchParams(next, { replace: true });
  };

  return (
    <select
      aria-label="Filter by tag"
      value={searchParams.get('tag') ?? ''}
      onChange={(e) => choose(e.target.value)}
    >
      <option value="">All tags</option>
      {tags.map((tag) => (
        <option key={tag.id} value={tag.id}>
          {tag.name}
        </option>
      ))}
    </select>
  );
}

function Toolbar({ view }: { view: PostView }) {
  const { search } = useLocation();
  return (
    <div className="blogs-toolbar">
      <nav className="blogs-tabs" aria-label="Post views">
        {TABS.map((tab) => (
          <Link
            key={tab.view}
            to={{ pathname: tab.to, search }}
            className={`blogs-tab${tab.view === view ? ' active' : ''}`}
            aria-current={tab.view === view ? 'page' : undefined}
          >
            {tab.label}
          </Link>
        ))}
      </nav>
      {view !== 'new' && <TagFilter />}
      <Link to="/blogs/sources" className="blogs-tab">
        Sources
      </Link>
    </div>
  );
}

function filtersFrom(searchParams: URLSearchParams, view: PostView): PostFilters {
  const directory = searchParams.get('directory');
  const filters: PostFilters = {};
  if (directory === UNFILED) filters.unfiled = true;
  else if (directory && directory !== ALL_DIRECTORIES) filters.directoryId = directory;
  const source = searchParams.get('source');
  if (source) filters.sourceId = source;
  const tag = searchParams.get('tag');
  if (tag && view !== 'new') filters.tagId = tag;
  return filters;
}

export default function BlogsPage({ view }: { view: PostView }) {
  const mode = useLayoutMode();
  const isMobile = mode === 'mobile';
  const { pathname } = useLocation();
  const [searchParams] = useSearchParams();
  const chosen = searchParams.has('directory') || searchParams.has('source');

  const posts = (
    <div className="blogs-main">
      <div className="blogs-content">
        <Toolbar view={view} />
        <PostList view={view} filters={filtersFrom(searchParams, view)} />
      </div>
    </div>
  );

  return (
    <div className="app-shell" data-layout={mode}>
      {isMobile ? (
        <MobileTopBar title="Blogs" backTo={chosen ? pathname : '/notebooks'} />
      ) : (
        <DesktopHeader />
      )}
      <main className="blogs-page">
        {isMobile ? (
          chosen ? posts : <BlogDirectoryList />
        ) : (
          <div className="blogs-layout">
            <BlogDirectoryList />
            {posts}
          </div>
        )}
      </main>
    </div>
  );
}
