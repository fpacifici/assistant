/**
 * Tag chips for a note, with an autocomplete input to add tags.
 *
 * Suggestions come from the caller's tag vocabulary (`GET /tag`). Typing a
 * name that matches no tag offers `Create "<name>"`, which tags the note by
 * name so the backend creates the tag on the fly. Matching is trimmed and
 * case-insensitive, like the backend.
 */

import { useId, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { addNoteTag, fetchTags, removeNoteTag } from '../api/tags';
import type { Note, Tag } from '../types';

const MAX_TAG_LENGTH = 64;

interface TagEditorProps {
  notebookId: string;
  noteId: string;
  tags: Tag[];
}

type Option = { kind: 'tag'; tag: Tag } | { kind: 'create'; name: string };

function normalize(name: string): string {
  return name.trim().toLowerCase();
}

export default function TagEditor({ notebookId, noteId, tags }: TagEditorProps) {
  const queryClient = useQueryClient();
  const listId = useId();
  const [text, setText] = useState('');
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const { data: allTags = [] } = useQuery({ queryKey: ['tags'], queryFn: fetchTags });

  const setNoteTags = (next: Tag[]) => {
    queryClient.setQueryData<Note>(['note', notebookId, noteId], (prev) =>
      prev ? { ...prev, tags: next } : prev,
    );
    queryClient.invalidateQueries({ queryKey: ['notes', notebookId] });
  };

  const addMutation = useMutation({
    mutationFn: (tag: { tagId: string } | { name: string }) =>
      addNoteTag(notebookId, noteId, tag),
    onSuccess: (next, tag) => {
      setNoteTags(next);
      if ('name' in tag) queryClient.invalidateQueries({ queryKey: ['tags'] });
      setError(null);
    },
    onError: (err) => setError(err instanceof Error ? err.message : String(err)),
  });

  const removeMutation = useMutation({
    mutationFn: (tagId: string) => removeNoteTag(notebookId, noteId, tagId),
    onSuccess: (_, tagId) => {
      setNoteTags(tags.filter((t) => t.id !== tagId));
      setError(null);
    },
    onError: (err) => setError(err instanceof Error ? err.message : String(err)),
  });

  const options = useMemo<Option[]>(() => {
    const query = normalize(text);
    const onNote = new Set(tags.map((t) => t.id));
    const matches = allTags.filter(
      (t) => !onNote.has(t.id) && normalize(t.name).includes(query),
    );
    const result: Option[] = matches.map((tag) => ({ kind: 'tag', tag }));
    const exact = allTags.some((t) => normalize(t.name) === query);
    if (query && !exact) result.push({ kind: 'create', name: text.trim() });
    return result;
  }, [text, tags, allTags]);

  const select = (option: Option) => {
    if (option.kind === 'tag') {
      addMutation.mutate({ tagId: option.tag.id });
    } else {
      if (option.name.length > MAX_TAG_LENGTH) {
        setError(`Tags can be at most ${MAX_TAG_LENGTH} characters`);
        return;
      }
      addMutation.mutate({ name: option.name });
    }
    setText('');
    setHighlighted(0);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setOpen(true);
      setHighlighted((h) => Math.max(Math.min(h + 1, options.length - 1), 0));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlighted((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const option = open ? options[highlighted] : undefined;
      if (option) {
        select(option);
      } else if (normalize(text)) {
        // The typed name is already one of the caller's tags (possibly
        // already on the note): tag by name, which the backend resolves.
        select({ kind: 'create', name: text.trim() });
      }
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  const showList = open && options.length > 0;
  const activeId = showList ? `${listId}-${highlighted}` : undefined;

  return (
    <div className="tag-editor">
      <ul className="tag-chips" aria-label="Tags">
        {tags.map((tag) => (
          <li key={tag.id} className="tag-chip">
            <span className="tag-chip-name">{tag.name}</span>
            <button
              type="button"
              className="tag-chip-remove"
              aria-label={`Remove tag ${tag.name}`}
              onClick={() => removeMutation.mutate(tag.id)}
            >
              ×
            </button>
          </li>
        ))}
      </ul>
      <div className="tag-input-wrap">
        <input
          type="text"
          className="tag-input"
          placeholder="Add tag"
          aria-label="Add tag"
          role="combobox"
          aria-expanded={showList}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={activeId}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setHighlighted(0);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={handleKeyDown}
        />
        {showList && (
          <ul className="tag-suggestions" id={listId} role="listbox">
            {options.map((option, i) => (
              <li
                key={option.kind === 'tag' ? option.tag.id : '__create__'}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === highlighted}
                className={`tag-suggestion${i === highlighted ? ' highlighted' : ''}`}
                // mousedown, not click: fires before the input's blur closes the list
                onMouseDown={(e) => {
                  e.preventDefault();
                  select(option);
                }}
                onMouseEnter={() => setHighlighted(i)}
              >
                {option.kind === 'tag' ? option.tag.name : `Create "${option.name}"`}
              </li>
            ))}
          </ul>
        )}
      </div>
      {error && <span className="status error tag-error">{error}</span>}
    </div>
  );
}
