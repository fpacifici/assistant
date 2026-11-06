/** `/blogs/sources`: add, edit, pause and delete sources, and manage directories. */

import { useState } from 'react';
import { Link } from 'react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  createDirectory,
  deleteDirectory,
  fetchDirectories,
  fetchSources,
  renameDirectory,
  updateSource,
} from '../api/blogs';
import ConfirmDialog from '../components/ConfirmDialog';
import DesktopHeader from '../components/DesktopHeader';
import MobileTopBar from '../components/MobileTopBar';
import DeleteSourceDialog from '../components/blogs/DeleteSourceDialog';
import SourceForm from '../components/blogs/SourceForm';
import { useLayoutMode } from '../layout/LayoutModeContext';
import type { BlogDirectory, BlogSource } from '../types';

function useInvalidateBlogs() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ['blogs'] });
}

function DirectoryRow({ directory }: { directory: BlogDirectory }) {
  const invalidate = useInvalidateBlogs();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(directory.name);
  const [deleting, setDeleting] = useState(false);

  const rename = useMutation({
    mutationFn: () => renameDirectory(directory.id, name.trim()),
    onSuccess: () => {
      void invalidate();
      setEditing(false);
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteDirectory(directory.id),
    onSuccess: invalidate,
  });

  if (editing) {
    return (
      <li className="directory-row">
        <form
          className="create-form"
          onSubmit={(e) => {
            e.preventDefault();
            rename.mutate();
          }}
        >
          <input
            aria-label={`New name for ${directory.name}`}
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          <button type="submit" disabled={!name.trim() || rename.isPending}>
            Save
          </button>
        </form>
        <button type="button" className="btn-cancel" onClick={() => setEditing(false)}>
          Cancel
        </button>
        {rename.isError && <p className="auth-error">{rename.error.message}</p>}
      </li>
    );
  }

  return (
    <li className="directory-row">
      <span className="directory-row-name">{directory.name}</span>
      <button
        type="button"
        className="btn-secondary"
        aria-label={`Rename ${directory.name}`}
        onClick={() => setEditing(true)}
      >
        Rename
      </button>
      <button
        type="button"
        className="btn-secondary"
        aria-label={`Delete ${directory.name}`}
        onClick={() => setDeleting(true)}
      >
        Delete
      </button>
      {deleting && (
        <ConfirmDialog
          message={`Delete the directory "${directory.name}"? Its blogs move to Unfiled.`}
          confirmLabel="Delete"
          onConfirm={() => {
            remove.mutate();
            setDeleting(false);
          }}
          onCancel={() => setDeleting(false)}
        />
      )}
    </li>
  );
}

function Directories() {
  const invalidate = useInvalidateBlogs();
  const [name, setName] = useState('');
  const { data: directories = [] } = useQuery({
    queryKey: ['blogs', 'directories'],
    queryFn: fetchDirectories,
  });
  const create = useMutation({
    mutationFn: () => createDirectory(name.trim()),
    onSuccess: () => {
      void invalidate();
      setName('');
    },
  });

  return (
    <section aria-label="Directories">
      <h2>Directories</h2>
      <form
        className="create-form"
        onSubmit={(e) => {
          e.preventDefault();
          create.mutate();
        }}
      >
        <input
          aria-label="Directory name"
          placeholder="New directory"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit" disabled={!name.trim() || create.isPending}>
          Add
        </button>
      </form>
      {create.isError && <p className="auth-error">{create.error.message}</p>}
      <ul className="blog-posts">
        {directories.map((directory) => (
          <DirectoryRow key={directory.id} directory={directory} />
        ))}
      </ul>
    </section>
  );
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

  return (
    <section aria-label="Blogs">
      <h2>Blogs</h2>
      {adding ? (
        <SourceForm onDone={() => setAdding(false)} onCancel={() => setAdding(false)} />
      ) : (
        <button
          type="button"
          className="btn-secondary blogs-add"
          onClick={() => setAdding(true)}
        >
          Add a blog
        </button>
      )}
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
        <Directories />
      </main>
    </div>
  );
}
