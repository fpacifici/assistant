/**
 * Promotes a link to a note: one the AI suggests, one found by keyword search,
 * or a new one in a notebook the user can add notes to. The link is marked
 * promoted and the note opens; nothing is written into the note. Copy as
 * markdown puts the link and its summary on the clipboard instead.
 */

import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchNotebooks } from '../../api/notebooks';
import { fetchSuggestions, promoteLink, READING_KEY } from '../../api/reading';
import type { PromoteTarget } from '../../api/reading';
import { searchNotes } from '../../api/search';
import type { ReadingLink } from '../../types';
import { linkMarkdown, linkTitle } from '../../lib/readingLinks';

const SEARCH_LIMIT = 10;

function Suggestions({
  link,
  onPick,
  disabled,
}: {
  link: ReadingLink;
  onPick: (target: PromoteTarget) => void;
  disabled: boolean;
}) {
  const { data, isPending, isError } = useQuery({
    queryKey: [...READING_KEY, 'suggestions', link.id],
    queryFn: () => fetchSuggestions(link.id),
    retry: false,
  });

  return (
    <section className="promote-section" aria-label="Suggested notes">
      <h4>Suggested notes</h4>
      {isPending && <p className="search-status">Finding related notes…</p>}
      {isError && <p className="search-status">Suggestions are not available.</p>}
      {data && data.length === 0 && <p className="search-status">No related notes found.</p>}
      {data && data.length > 0 && (
        <ul className="promote-notes">
          {data.map((suggestion) => (
            <li key={suggestion.note_id}>
              <button
                type="button"
                className="promote-note"
                disabled={disabled}
                onClick={() => onPick({ noteId: suggestion.note_id })}
              >
                <span className="promote-note-title">{suggestion.title || 'Untitled'}</span>
                <span className="promote-note-notebook">{suggestion.notebook_name}</span>
                <span className="promote-note-passage">{suggestion.passage}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function Search({
  onPick,
  disabled,
}: {
  onPick: (target: PromoteTarget) => void;
  disabled: boolean;
}) {
  const [input, setInput] = useState('');
  const [query, setQuery] = useState('');
  const { data, isFetching, isError } = useQuery({
    queryKey: ['search', 'promote', query],
    queryFn: () => searchNotes(query, { offset: 0, limit: SEARCH_LIMIT }),
    enabled: query !== '',
  });

  return (
    <section className="promote-section" aria-label="Search notes">
      <h4>Search</h4>
      <form
        className="promote-row"
        onSubmit={(e) => {
          e.preventDefault();
          setQuery(input.trim());
        }}
      >
        <input
          type="search"
          aria-label="Search your notes"
          placeholder="Words, &quot;phrases&quot;, tag:name"
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" className="btn-secondary" disabled={!input.trim()}>
          Search
        </button>
      </form>
      {isFetching && <p className="search-status">Searching…</p>}
      {isError && <p className="search-status auth-error">Could not search.</p>}
      {data && !isFetching && data.results.length === 0 && (
        <p className="search-status">No notes found.</p>
      )}
      {data && data.results.length > 0 && (
        <ul className="promote-notes">
          {data.results.map((result) => {
            const editable = result.note.permissions.includes('update');
            return (
              <li key={result.note.id}>
                <button
                  type="button"
                  className="promote-note"
                  disabled={disabled || !editable}
                  title={editable ? undefined : 'You can only view this note'}
                  onClick={() => onPick({ noteId: result.note.id })}
                >
                  <span className="promote-note-title">{result.note.title || 'Untitled'}</span>
                  <span className="promote-note-notebook">
                    {result.notebook.name}
                    {!editable && ' · view only'}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

function NewNote({
  link,
  onPick,
  disabled,
}: {
  link: ReadingLink;
  onPick: (target: PromoteTarget) => void;
  disabled: boolean;
}) {
  const [title, setTitle] = useState(link.title ?? '');
  const [notebookId, setNotebookId] = useState('');
  const { data: notebooks = [] } = useQuery({
    queryKey: ['notebooks', 'all'],
    queryFn: () => fetchNotebooks(0, 100),
  });
  const writable = notebooks.filter((notebook) =>
    notebook.permissions.includes('create_notes'),
  );
  const chosen = notebookId || writable[0]?.id || '';

  return (
    <section className="promote-section" aria-label="New note">
      <h4>New note</h4>
      <form
        className="promote-row"
        onSubmit={(e) => {
          e.preventDefault();
          onPick({ notebookId: chosen, title: title.trim() });
        }}
      >
        <input
          aria-label="Note title"
          placeholder="Title"
          maxLength={500}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
        />
        <select
          aria-label="Notebook"
          value={chosen}
          onChange={(e) => setNotebookId(e.target.value)}
        >
          {writable.map((notebook) => (
            <option key={notebook.id} value={notebook.id}>
              {notebook.name}
            </option>
          ))}
        </select>
        <button
          type="submit"
          className="btn-secondary"
          disabled={disabled || !title.trim() || !chosen}
        >
          Create
        </button>
      </form>
      {writable.length === 0 && (
        <p className="search-status">No notebook you can add notes to.</p>
      )}
    </section>
  );
}

export default function PromoteDialog({
  link,
  onClose,
}: {
  link: ReadingLink;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [copied, setCopied] = useState<'done' | 'failed' | null>(null);

  const promote = useMutation({
    mutationFn: (target: PromoteTarget) => promoteLink(link.id, target),
    onSuccess: (result) => {
      void queryClient.invalidateQueries({ queryKey: [...READING_KEY] });
      onClose();
      navigate(`/notebooks/${result.notebook_id}/notes/${result.note_id}`);
    },
  });

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(linkMarkdown(link));
      setCopied('done');
    } catch {
      setCopied('failed');
    }
  };

  const pick = (target: PromoteTarget) => promote.mutate(target);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal promote-dialog"
        role="dialog"
        aria-modal="true"
        aria-label={`Promote ${linkTitle(link)}`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h3>Promote to a note</h3>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>
        <p className="promote-link-title">{linkTitle(link)}</p>
        {promote.isError && <p className="auth-error">{promote.error.message}</p>}
        <Suggestions link={link} onPick={pick} disabled={promote.isPending} />
        <Search onPick={pick} disabled={promote.isPending} />
        <NewNote link={link} onPick={pick} disabled={promote.isPending} />
        <div className="promote-footer">
          <button type="button" className="btn-secondary" onClick={() => void copy()}>
            Copy as markdown
          </button>
          {copied === 'done' && <span role="status">Copied</span>}
          {copied === 'failed' && <span role="status">Could not copy</span>}
        </div>
      </div>
    </div>
  );
}
