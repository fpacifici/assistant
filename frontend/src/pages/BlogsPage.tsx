/**
 * Blog posts: Triage (`/blogs/triage`), All (`/blogs`) and Relevant
 * (`/blogs/relevant`). The filters live in the URL: `?category=` (an id,
 * `unfiled` or `all`), `?source=` (an archived source), `?tag=` and `?read=`
 * (`read` or `unread`).
 *
 * Triage shows the new posts of every category at once, with a category
 * picker in the toolbar instead of the sidebar. Its tab always opens it on
 * all categories.
 *
 * Desktop: the app header above a category sidebar and the posts. Mobile: one
 * level at a time, the categories, then the posts of the chosen one; Triage
 * goes straight to the posts. TUI mode shows the desktop page.
 */

import { Link, useLocation, useSearchParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import type { PostFilters } from '../api/blogs';
import { CATEGORIES_KEY, fetchCategories } from '../api/categories';
import { fetchTags } from '../api/tags';
import CategoryList, { ALL_CATEGORIES, UNFILED } from '../components/blogs/CategoryList';
import PostList from '../components/blogs/PostList';
import DesktopHeader from '../components/DesktopHeader';
import MobileTopBar from '../components/MobileTopBar';
import { useLayoutMode } from '../layout/LayoutModeContext';
import type { PostView } from '../types';

export const READ = 'read';
export const UNREAD = 'unread';

const TABS: { view: PostView; to: string; label: string }[] = [
  { view: 'new', to: '/blogs/triage', label: 'Triage' },
  { view: 'all', to: '/blogs', label: 'All' },
  { view: 'relevant', to: '/blogs/relevant', label: 'Relevant' },
];

/** A `<select>` bound to one search parameter; the empty value removes it. */
function ParamSelect({
  param,
  label,
  children,
}: {
  param: string;
  label: string;
  children: React.ReactNode;
}) {
  const [searchParams, setSearchParams] = useSearchParams();

  const choose = (value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(param, value);
    else next.delete(param);
    setSearchParams(next, { replace: true });
  };

  return (
    <select
      aria-label={label}
      value={searchParams.get(param) ?? ''}
      onChange={(e) => choose(e.target.value)}
    >
      {children}
    </select>
  );
}

function TagFilter() {
  const { data: tags = [] } = useQuery({ queryKey: ['tags'], queryFn: fetchTags });
  return (
    <ParamSelect param="tag" label="Filter by tag">
      <option value="">All tags</option>
      {tags.map((tag) => (
        <option key={tag.id} value={tag.id}>
          {tag.name}
        </option>
      ))}
    </ParamSelect>
  );
}

function ReadFilter() {
  return (
    <ParamSelect param="read" label="Filter by read">
      <option value="">Read and to read</option>
      <option value={UNREAD}>To read</option>
      <option value={READ}>Read</option>
    </ParamSelect>
  );
}

function CategoryFilter() {
  const { data: categories = [] } = useQuery({
    queryKey: [...CATEGORIES_KEY],
    queryFn: fetchCategories,
  });
  return (
    <ParamSelect param="category" label="Filter by category">
      <option value="">All categories</option>
      {categories.map((category) => (
        <option key={category.id} value={category.id}>
          {category.name}
        </option>
      ))}
      <option value={UNFILED}>Unfiled</option>
    </ParamSelect>
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
            // Triage always opens on every category.
            to={{ pathname: tab.to, search: tab.view === 'new' ? '' : search }}
            className={`blogs-tab${tab.view === view ? ' active' : ''}`}
            aria-current={tab.view === view ? 'page' : undefined}
          >
            {tab.label}
          </Link>
        ))}
      </nav>
      {view === 'new' ? (
        <CategoryFilter />
      ) : (
        <>
          <ReadFilter />
          <TagFilter />
        </>
      )}
      <Link to="/blogs/sources" className="blogs-tab">
        Sources
      </Link>
    </div>
  );
}

function filtersFrom(searchParams: URLSearchParams, view: PostView): PostFilters {
  const category = searchParams.get('category');
  const filters: PostFilters = {};
  if (category === UNFILED) filters.unfiled = true;
  else if (category && category !== ALL_CATEGORIES) filters.categoryId = category;
  if (view === 'new') return filters;
  const source = searchParams.get('source');
  if (source) filters.sourceId = source;
  const tag = searchParams.get('tag');
  if (tag) filters.tagId = tag;
  const read = searchParams.get('read');
  if (read === READ) filters.read = true;
  else if (read === UNREAD) filters.read = false;
  return filters;
}

export default function BlogsPage({ view }: { view: PostView }) {
  const mode = useLayoutMode();
  const isMobile = mode === 'mobile';
  const triage = view === 'new';
  const { pathname } = useLocation();
  const [searchParams] = useSearchParams();
  const chosen = triage || searchParams.has('category') || searchParams.has('source');

  const posts = (
    <div className="blogs-main">
      <div className="blogs-content">
        <Toolbar view={view} />
        <PostList view={view} filters={filtersFrom(searchParams, view)} />
      </div>
    </div>
  );

  const backTo = !triage && chosen ? pathname : '/notebooks';

  return (
    <div className="app-shell" data-layout={mode}>
      {isMobile ? <MobileTopBar title="Blogs" backTo={backTo} /> : <DesktopHeader />}
      <main className="blogs-page">
        {isMobile ? (
          chosen ? posts : <CategoryList />
        ) : triage ? (
          posts
        ) : (
          <div className="blogs-layout">
            <CategoryList />
            {posts}
          </div>
        )}
      </main>
    </div>
  );
}
