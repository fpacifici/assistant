/** `/blogs/sources`: add, edit, pause and delete sources, open their collection
 * history, and manage categories. */

import { useState } from 'react';
import { Link } from 'react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchSources, updateSource } from '../api/blogs';
import DesktopHeader from '../components/DesktopHeader';
import ManageCategoriesDialog from '../components/ManageCategoriesDialog';
import MobileTopBar from '../components/MobileTopBar';
import DeleteSourceDialog from '../components/blogs/DeleteSourceDialog';
import SourceForm from '../components/blogs/SourceForm';
import { useLayoutMode } from '../layout/LayoutModeContext';
import type { BlogSource } from '../types';

function useInvalidateBlogs() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ['blogs'] });
}

/** What the source list says about the last collection. */
function SourceStatus({ source }: { source: BlogSource }) {
  if (source.last_error) {
    return <span className="source-row-status error">{source.last_error}</span>;
  }
  if (!source.enabled) return <span className="source-row-status">Paused</span>;
  if (!source.last_fetched_at) {
    return <span className="source-row-status">Waiting for first collection</span>;
  }
  return (
    <span className="source-row-status">
      Last collected {new Date(source.last_fetched_at).toLocaleString()}
    </span>
  );
}

function SourceRow({ source }: { source: BlogSource }) {
  const invalidate = useInvalidateBlogs();
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const togglePause = useMutation({
    mutationFn: () => updateSource(source.id, { enabled: !source.enabled }),
    onSuccess: invalidate,
  });

  if (editing) {
    return (
      <li>
        <SourceForm
          source={source}
          onDone={() => setEditing(false)}
          onCancel={() => setEditing(false)}
        />
      </li>
    );
  }

  return (
    <li className="source-row">
      <div className="source-row-info">
        <div className="source-row-title">{source.title}</div>
        <SourceStatus source={source} />
      </div>
      <div className="source-row-actions">
        <Link
          to={`/blogs/sources/${source.id}/log`}
          className="btn-secondary"
          aria-label={`History of ${source.title}`}
        >
          History
        </Link>
        <button
          type="button"
          className="btn-secondary"
          aria-label={`Edit ${source.title}`}
          onClick={() => setEditing(true)}
        >
          Edit
        </button>
        <button
          type="button"
          className="btn-secondary"
          aria-label={`${source.enabled ? 'Pause' : 'Resume'} ${source.title}`}
          disabled={togglePause.isPending}
          onClick={() => togglePause.mutate()}
        >
          {source.enabled ? 'Pause' : 'Resume'}
        </button>
        <button
          type="button"
          className="btn-secondary"
          aria-label={`Delete ${source.title}`}
          onClick={() => setDeleting(true)}
        >
          Delete
        </button>
      </div>
      {deleting && <DeleteSourceDialog source={source} onClose={() => setDeleting(false)} />}
    </li>
  );
}

function Sources() {
  const { data: sources = [], isPending } = useQuery({
    queryKey: ['blogs', 'sources'],
    queryFn: () => fetchSources(),
  });
  const [adding, setAdding] = useState(false);
  const [managing, setManaging] = useState(false);

  return (
    <section aria-label="Blogs">
      <h2>Blogs</h2>
      {adding ? (
        <SourceForm onDone={() => setAdding(false)} onCancel={() => setAdding(false)} />
      ) : (
        <div className="blogs-add-row">
          <button
            type="button"
            className="btn-secondary blogs-add"
            onClick={() => setAdding(true)}
          >
            Add a blog
          </button>
          <button
            type="button"
            className="btn-secondary blogs-add"
            onClick={() => setManaging(true)}
          >
            Manage categories
          </button>
        </div>
      )}
      {managing && <ManageCategoriesDialog onClose={() => setManaging(false)} />}
      {!isPending && sources.length === 0 && !adding && <p className="empty">No blogs yet</p>}
      <ul className="blog-posts">
        {sources.map((source) => (
          <SourceRow key={source.id} source={source} />
        ))}
      </ul>
    </section>
  );
}

export default function BlogSourcesPage() {
  const mode = useLayoutMode();
  const isMobile = mode === 'mobile';
  return (
    <div className="app-shell" data-layout={mode}>
      {isMobile ? <MobileTopBar title="Sources" backTo="/blogs" /> : <DesktopHeader />}
      <main className="blog-sources-page">
        {!isMobile && (
          <p>
            <Link to="/blogs">&larr; Back to posts</Link>
          </p>
        )}
        <Sources />
      </main>
    </div>
  );
}
