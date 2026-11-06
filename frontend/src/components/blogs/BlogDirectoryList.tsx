/** The post filters: every directory, Unfiled, and archived sources that still have useful posts. */

import { Link, useLocation, useSearchParams } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { fetchDirectories, fetchSources } from '../../api/blogs';

export const ALL_DIRECTORIES = 'all';
export const UNFILED = 'unfiled';

export default function BlogDirectoryList() {
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const selectedDirectory = searchParams.get('directory');
  const selectedSource = searchParams.get('source');

  const { data: directories = [] } = useQuery({
    queryKey: ['blogs', 'directories'],
    queryFn: fetchDirectories,
  });
  const { data: archived = [] } = useQuery({
    queryKey: ['blogs', 'sources', 'archived'],
    queryFn: () => fetchSources({ archived: true }),
  });

  const search = (key: 'directory' | 'source', value: string) => {
    const next = new URLSearchParams(searchParams);
    next.delete('directory');
    next.delete('source');
    next.set(key, value);
    return `?${next}`;
  };

  const directoryLink = (value: string, label: string, active: boolean) => (
    <li key={value}>
      <Link
        to={{ pathname: location.pathname, search: search('directory', value) }}
        className={`blog-directory-link${active ? ' active' : ''}`}
        aria-current={active ? 'true' : undefined}
      >
        {label}
      </Link>
    </li>
  );

  const allActive =
    !selectedSource && (selectedDirectory === null || selectedDirectory === ALL_DIRECTORIES);

  return (
    <nav className="blog-directories" aria-label="Directories">
      <ul>
        {directoryLink(ALL_DIRECTORIES, 'All directories', allActive)}
        {directories.map((directory) =>
          directoryLink(directory.id, directory.name, selectedDirectory === directory.id),
        )}
        {directoryLink(UNFILED, 'Unfiled', selectedDirectory === UNFILED)}
      </ul>
      {archived.length > 0 && (
        <>
          <h2>Archived sources</h2>
          <ul>
            {archived.map((source) => (
              <li key={source.id}>
                <Link
                  to={{ pathname: location.pathname, search: search('source', source.id) }}
                  className={`blog-directory-link${selectedSource === source.id ? ' active' : ''}`}
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
