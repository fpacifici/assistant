/** The post filters: every category, Unfiled, and archived sources that still have useful posts. */

import { Link, useLocation, useSearchParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { fetchSources } from '../../api/blogs';
import { CATEGORIES_KEY, fetchCategories } from '../../api/categories';

export const ALL_CATEGORIES = 'all';
export const UNFILED = 'unfiled';

export default function CategoryList() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const selectedCategory = searchParams.get('category');
  const selectedSource = searchParams.get('source');

  const { data: categories = [] } = useQuery({
    queryKey: [...CATEGORIES_KEY],
    queryFn: fetchCategories,
  });
  const { data: archived = [] } = useQuery({
    queryKey: ['blogs', 'sources', 'archived'],
    queryFn: () => fetchSources({ archived: true }),
  });

  const search = (key: 'category' | 'source', value: string) => {
    const next = new URLSearchParams(searchParams);
    next.delete('category');
    next.delete('source');
    next.set(key, value);
    return `?${next}`;
  };

  const categoryLink = (value: string, label: string, active: boolean) => (
    <li key={value}>
      <Link
        to={{ pathname: location.pathname, search: search('category', value) }}
        className={`blog-category-link${active ? ' active' : ''}`}
        aria-current={active ? 'true' : undefined}
      >
        {label}
      </Link>
    </li>
  );

  const allActive =
    !selectedSource && (selectedCategory === null || selectedCategory === ALL_CATEGORIES);

  return (
    <nav className="blog-categories" aria-label="Categories">
      <ul>
        {categoryLink(ALL_CATEGORIES, 'All categories', allActive)}
        {categories.map((category) =>
          categoryLink(category.id, category.name, selectedCategory === category.id),
        )}
        {categoryLink(UNFILED, 'Unfiled', selectedCategory === UNFILED)}
      </ul>
      {archived.length > 0 && (
        <>
          <h2>Archived sources</h2>
          <ul>
            {archived.map((source) => (
              <li key={source.id}>
                <Link
                  to={{ pathname: location.pathname, search: search('source', source.id) }}
                  className={`blog-category-link${selectedSource === source.id ? ' active' : ''}`}
                  aria-current={selectedSource === source.id ? 'true' : undefined}
                >
                  {source.title}
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </nav>
  );
}
