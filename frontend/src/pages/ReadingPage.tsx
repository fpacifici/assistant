/**
 * The reading list: To read (`/reading`), Archive (`/reading/archive`) and
 * Promoted (`/reading/promoted`). `?category=` (an id or `unfiled`) narrows
 * any view to one category.
 *
 * To read shows one collapsible section per category that has links, then
 * Unfiled, each oldest first. Archive and Promoted are one list, most
 * recently decided first.
 *
 * Desktop: the app header above a category sidebar and the links. Mobile: the
 * sidebar becomes a category picker in the toolbar. TUI mode shows the
 * desktop page.
 */

import { useState } from 'react';
import { Link, useLocation, useSearchParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { CATEGORIES_KEY, fetchCategories } from '../api/categories';
import { fetchLinkCounts, READING_KEY } from '../api/reading';
import type { LinkFilter } from '../api/reading';
import DesktopHeader from '../components/DesktopHeader';
import ManageCategoriesDialog from '../components/ManageCategoriesDialog';
import MobileTopBar from '../components/MobileTopBar';
import AddLinkBox from '../components/reading/AddLinkBox';
import LinkList from '../components/reading/LinkList';
import PromoteDialog from '../components/reading/PromoteDialog';
import { useLayoutMode } from '../layout/LayoutModeContext';
import type { Category, CategoryCount, LinkState, ReadingLink } from '../types';

export const UNFILED = 'unfiled';

const VIEWS: { state: LinkState; to: string; label: string; empty: string }[] = [
  { state: 'to_read', to: '/reading', label: 'To read', empty: 'Nothing to read. Add a link above.' },
  { state: 'discarded', to: '/reading/archive', label: 'Archive', empty: 'Discarded links appear here.' },
  { state: 'promoted', to: '/reading/promoted', label: 'Promoted', empty: 'Links you promote to notes appear here.' },
];

function filterFor(category: string | null): LinkFilter {
  if (category === UNFILED) return { unfiled: true };
  if (category) return { categoryId: category };
  return {};
}

function countOf(counts: CategoryCount[], categoryId: string | null): number {
  return counts.find((count) => count.category_id === categoryId)?.count ?? 0;
}

/** Desktop sidebar: every category with its count, Unfiled, and Manage categories. */
function CategorySidebar({
  categories,
  counts,
  selected,
  onManage,
}: {
  categories: Category[];
  counts: CategoryCount[];
  selected: string | null;
  onManage: () => void;
}) {
  const { pathname } = useLocation();
  const total = counts.reduce((sum, count) => sum + count.count, 0);
  const item = (value: string | null, label: string, count: number) => {
    const active = selected === value;
    return (
      <li key={value ?? 'all'}>
        <Link
          to={{ pathname, search: value ? `?category=${value}` : '' }}
          className={`blog-category-link${active ? ' active' : ''}`}
          aria-current={active ? 'true' : undefined}
        >
          <span>{label}</span>
          <span className="reading-count">{count}</span>
        </Link>
      </li>
    );
  };
  return (
    <nav className="blog-categories" aria-label="Categories">
      <ul>
        {item(null, 'All categories', total)}
        {categories.map((category) =>
          item(category.id, category.name, countOf(counts, category.id)),
        )}
        {item(UNFILED, 'Unfiled', countOf(counts, null))}
      </ul>
      <button type="button" className="btn-secondary reading-manage" onClick={onManage}>
        Manage categories
      </button>
    </nav>
  );
}

/** Mobile: the sidebar as a picker, with the same counts. */
function CategoryPicker({
  categories,
  counts,
}: {
  categories: Category[];
  counts: CategoryCount[];
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  return (
    <select
      aria-label="Filter by category"
      value={searchParams.get('category') ?? ''}
      onChange={(e) => {
        const next = new URLSearchParams(searchParams);
        if (e.target.value) next.set('category', e.target.value);
        else next.delete('category');
        setSearchParams(next, { replace: true });
      }}
    >
      <option value="">
        All categories ({counts.reduce((sum, count) => sum + count.count, 0)})
      </option>
      {categories.map((category) => (
        <option key={category.id} value={category.id}>
          {category.name} ({countOf(counts, category.id)})
        </option>
      ))}
      <option value={UNFILED}>Unfiled ({countOf(counts, null)})</option>
    </select>
  );
}

/** One category's links to read, under a header that folds them away. */
function Section({
  title,
  count,
  filter,
  categories,
  onPromote,
}: {
  title: string;
  count: number;
  filter: LinkFilter;
  categories: Category[];
  onPromote: (link: ReadingLink) => void;
}) {
  const [open, setOpen] = useState(true);
  return (
    <section className="reading-section" aria-label={title}>
      <h2>
        <button type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
          <span aria-hidden="true">{open ? '▾' : '▸'}</span> {title}{' '}
          <span className="reading-count">{count}</span>
        </button>
      </h2>
      {open && (
        <LinkList
          state="to_read"
          filter={filter}
          categories={categories}
          emptyText="Nothing left here."
          onPromote={onPromote}
        />
      )}
    </section>
  );
}

export default function ReadingPage({ state }: { state: LinkState }) {
  const mode = useLayoutMode();
  const isMobile = mode === 'mobile';
  const { search } = useLocation();
  const [searchParams] = useSearchParams();
  const selected = searchParams.get('category');
  const [promoting, setPromoting] = useState<ReadingLink | null>(null);
  const [managing, setManaging] = useState(false);
  const view = VIEWS.find((item) => item.state === state) ?? VIEWS[0];

  const { data: categories = [] } = useQuery({
    queryKey: [...CATEGORIES_KEY],
    queryFn: fetchCategories,
  });
  const { data: counts = [], isPending: countsPending } = useQuery({
    queryKey: [...READING_KEY, 'counts', state],
    queryFn: () => fetchLinkCounts(state),
  });

  const sections = [
    ...categories.map((category) => ({
      key: category.id,
      title: category.name,
      filter: { categoryId: category.id } as LinkFilter,
      count: countOf(counts, category.id),
    })),
    { key: UNFILED, title: 'Unfiled', filter: { unfiled: true } as LinkFilter, count: countOf(counts, null) },
  ].filter((section) => section.count > 0);

  let links: React.ReactNode;
  if (state === 'to_read' && !selected) {
    links = countsPending ? (
      <p className="search-status">Loading…</p>
    ) : sections.length === 0 ? (
      <p className="search-status">{view.empty}</p>
    ) : (
      sections.map((section) => (
        <Section
          key={section.key}
          title={section.title}
          count={section.count}
          filter={section.filter}
          categories={categories}
          onPromote={setPromoting}
        />
      ))
    );
  } else {
    links = (
      <LinkList
        state={state}
        filter={filterFor(selected)}
        categories={categories}
        emptyText={view.empty}
        onPromote={setPromoting}
      />
    );
  }

  const content = (
    <div className="blogs-main">
      <div className="blogs-content">
        <div className="blogs-toolbar">
          <nav className="blogs-tabs" aria-label="Reading views">
            {VIEWS.map((item) => (
              <Link
                key={item.state}
                to={{ pathname: item.to, search }}
                className={`blogs-tab${item.state === state ? ' active' : ''}`}
                aria-current={item.state === state ? 'page' : undefined}
              >
                {item.label}
              </Link>
            ))}
          </nav>
          {isMobile && (
            <>
              <CategoryPicker categories={categories} counts={counts} />
              <button
                type="button"
                className="btn-secondary reading-manage"
                onClick={() => setManaging(true)}
              >
                Manage categories
              </button>
            </>
          )}
        </div>
        {state === 'to_read' && <AddLinkBox />}
        {links}
      </div>
    </div>
  );

  return (
    <div className="app-shell" data-layout={mode}>
      {isMobile ? (
        <MobileTopBar title="Reading" backTo="/notebooks" />
      ) : (
        <DesktopHeader />
      )}
      <main className="blogs-page">
        {isMobile ? (
          content
        ) : (
          <div className="blogs-layout reading-layout">
            <CategorySidebar
              categories={categories}
              counts={counts}
              selected={selected}
              onManage={() => setManaging(true)}
            />
            {content}
          </div>
        )}
      </main>
      {promoting && <PromoteDialog link={promoting} onClose={() => setPromoting(null)} />}
      {managing && <ManageCategoriesDialog onClose={() => setManaging(false)} />}
    </div>
  );
}
