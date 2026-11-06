/** The tags of a note: `TagChips`, applied to the note and its cached lists. */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { addNoteTag, removeNoteTag } from '../api/tags';
import type { Note, Tag } from '../types';
import TagChips from './TagChips';
import type { TagChoice } from './TagChips';

interface TagEditorProps {
  notebookId: string;
  noteId: string;
  tags: Tag[];
}

export default function TagEditor({ notebookId, noteId, tags }: TagEditorProps) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);

  const setNoteTags = (next: Tag[]) => {
    queryClient.setQueryData<Note>(['note', notebookId, noteId], (prev) =>
      prev ? { ...prev, tags: next } : prev,
    );
    queryClient.invalidateQueries({ queryKey: ['notes', notebookId] });
  };

  const addMutation = useMutation({
    mutationFn: (tag: TagChoice) => addNoteTag(notebookId, noteId, tag),
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

  return (
    <TagChips
      tags={tags}
      onAdd={(tag) => addMutation.mutate(tag)}
      onRemove={(tagId) => removeMutation.mutate(tagId)}
      error={error}
    />
  );
}
