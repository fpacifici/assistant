/**
 * One reading link: title (opens the URL in a new tab), domain, type, added
 * date, analysis status, summary, a category picker, the user's notes, and
 * the actions valid for its state. Everything that came from the page or the
 * model is rendered as text.
 */

import { useState } from 'react';
import { Link } from 'react-router';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  deleteLink,
  discardLink,
  READING_KEY,
  restoreLink,
  retryLink,
  updateLink,
} from '../../api/reading';
import type { LinkChanges } from '../../api/reading';
import { linkDomain, linkTitle } from '../../lib/readingLinks';
import { isSafeLink } from '../../lib/safeLink';
import type { Category, LinkType, ReadingLink } from '../../types';
import ConfirmDialog from '../ConfirmDialog';

const TYPE_LABELS: Record<LinkType, { icon: string; label: string }> = {
  web: { icon: '🌐', label: 'Web page' },
  pdf: { icon: '📄', label: 'PDF' },
  text: { icon: '📝', label: 'Text' },
  youtube: { icon: '▶', label: 'Video' },
  other: { icon: '📦', label: 'File' },
};

function Status({ link }: { link: ReadingLink }) {
  switch (link.analysis_status) {
    case 'pending':
      return <span className="link-status pending">Analyzing…</span>;
    case 'failed':
      return <span className="link-status failed">Analysis failed</span>;
    case 'not_summarizable':
      return <span className="link-status">No summary</span>;
    default:
      return null;
  }
}

function Summary({ link }: { link: ReadingLink }) {
  if (link.summary) return <p className="post-card-summary">{link.summary}</p>;
  if (link.analysis_status === 'pending') return null;
  const reason =
    link.analysis_status === 'failed'
      ? `Could not analyze this link${link.last_error ? `: ${link.last_error}` : ''}.`
      : 'Not summarized: filed from its title and address.';
  return <p className="post-card-summary unavailable">{reason}</p>;
}

function Title({
  link,
  onSave,
}: {
  link: ReadingLink;
  onSave: (title: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(link.title ?? '');
  const title = linkTitle(link);

  if (editing) {
    return (
      <form
        className="link-title-form"
        onSubmit={(e) => {
          e.preventDefault();
          onSave(value.trim());
          setEditing(false);
        }}
      >
        <input
          aria-label="Title"
          value={value}
          maxLength={1024}
          placeholder="Blank for the automatic title"
          onChange={(e) => setValue(e.target.value)}
          autoFocus
        />
        <button type="submit" className="btn-secondary">
          Save
        </button>
        <button type="button" className="btn-cancel" onClick={() => setEditing(false)}>
          Cancel
        </button>
      </form>
    );
  }

  return (
    <div className="link-title-row">
      {isSafeLink(link.url) ? (
        <a href={link.url} target="_blank" rel="noopener noreferrer" className="post-card-title">
          {title}
        </a>
      ) : (
        <span className="post-card-title plain">{title}</span>
      )}
      <button
        type="button"
        className="link-edit-title"
        aria-label={`Edit title of ${title}`}
        onClick={() => {
          setValue(link.title ?? '');
          setEditing(true);
        }}
      >
        ✎
      </button>
    </div>
  );
}

function Notes({ link, onSave }: { link: ReadingLink; onSave: (notes: string) => void }) {
  const [value, setValue] = useState(link.user_notes ?? '');
  return (
    <textarea
      className="link-notes"
      aria-label={`Notes on ${linkTitle(link)}`}
      placeholder="Your notes"
      rows={value ? 2 : 1}
      maxLength={10000}
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => {
        if (value.trim() !== (link.user_notes ?? '')) onSave(value);
      }}
    />
  );
}

interface LinkCardProps {
  link: ReadingLink;
  categories: Category[];
  onPromote: (link: ReadingLink) => void;
}

export default function LinkCard({ link, categories, onPromote }: LinkCardProps) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const title = linkTitle(link);

  const handlers = {
    onSuccess: () => {
      setError(null);
      return queryClient.invalidateQueries({ queryKey: [...READING_KEY] });
    },
    onError: (err: Error) => setError(err.message),
  };
  const update = useMutation({
    mutationFn: (changes: LinkChanges) => updateLink(link.id, changes),
    ...handlers,
  });
  const discard = useMutation({ mutationFn: () => discardLink(link.id), ...handlers });
  const restore = useMutation({ mutationFn: () => restoreLink(link.id), ...handlers });
  const retry = useMutation({ mutationFn: () => retryLink(link.id), ...handlers });
  const remove = useMutation({ mutationFn: () => deleteLink(link.id), ...handlers });

  const type = link.link_type ? TYPE_LABELS[link.link_type] : null;
  const busy =
    update.isPending ||
    discard.isPending ||
    restore.isPending ||
    retry.isPending ||
    remove.isPending;

  return (
    <li className={`post-card link-card${link.analysis_status === 'pending' ? ' pending' : ''}`}>
      <Title link={link} onSave={(value) => update.mutate({ title: value || null })} />
      <div className="post-card-meta">
        {type && (
          <span className="link-type" title={type.label}>
            <span aria-hidden="true">{type.icon}</span> {type.label}
          </span>
        )}
        <span>{linkDomain(link.url)}</span>
        <time dateTime={link.created_at}>
          Added {new Date(link.created_at).toLocaleDateString()}
        </time>
        <Status link={link} />
      </div>
      <Summary link={link} />
      <div className="link-fields">
        <label className="link-category">
          <span>Category</span>
          <select
            aria-label={`Category of ${title}`}
            value={link.category_id ?? ''}
            disabled={busy}
            onChange={(e) => update.mutate({ category_id: e.target.value || null })}
          >
            <option value="">Unfiled</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </label>
        <Notes link={link} onSave={(notes) => update.mutate({ user_notes: notes })} />
      </div>
      {error && <p className="auth-error">{error}</p>}
      <div className="post-actions link-actions">
        {isSafeLink(link.url) && (
          <a
            className="btn-secondary"
            href={link.url}
            target="_blank"
            rel="noopener noreferrer"
            aria-label={`Open ${title}`}
          >
            Open
          </a>
        )}
        {link.state === 'to_read' && (
          <>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => onPromote(link)}
            >
              Promote
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={busy}
              onClick={() => discard.mutate()}
            >
              Discard
            </button>
          </>
        )}
        {link.state === 'discarded' && (
          <button
            type="button"
            className="btn-secondary"
            disabled={busy}
            onClick={() => restore.mutate()}
          >
            Restore
          </button>
        )}
        {link.state === 'promoted' &&
          (link.note_id && link.note_notebook_id ? (
            <Link
              className="btn-secondary"
              to={`/notebooks/${link.note_notebook_id}/notes/${link.note_id}`}
            >
              Open note
            </Link>
          ) : (
            <span className="link-status">Note deleted</span>
          ))}
        {link.analysis_status !== 'pending' && (
          <button
            type="button"
            className="btn-secondary"
            disabled={busy}
            onClick={() => retry.mutate()}
          >
            Retry analysis
          </button>
        )}
        {link.state !== 'to_read' && (
          <button
            type="button"
            className="btn-secondary"
            disabled={busy}
            onClick={() => setDeleting(true)}
          >
            Delete
          </button>
        )}
      </div>
      {deleting && (
        <ConfirmDialog
          message={`Delete "${title}"?${link.state === 'promoted' ? ' Its note stays.' : ''}`}
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
