/**
 * Adds a source, or edits one when `source` is given. URL and look back are
 * only asked at creation: they can't change afterwards.
 */

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { createSource, updateSource } from '../../api/blogs';
import { CATEGORIES_KEY, fetchCategories } from '../../api/categories';
import type { BlogSource } from '../../types';

const DEFAULT_LOOKBACK_DAYS = 7;

interface SourceFormProps {
  source?: BlogSource;
  onDone: () => void;
  onCancel?: () => void;
}

export default function SourceForm({ source, onDone, onCancel }: SourceFormProps) {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState(source?.title ?? '');
  const [remarks, setRemarks] = useState(source?.remarks ?? '');
  const [preferences, setPreferences] = useState(source?.preferences ?? '');
  const [categoryId, setCategoryId] = useState(source?.category_id ?? '');
  const [lookbackDays, setLookbackDays] = useState(DEFAULT_LOOKBACK_DAYS);

  const { data: categories = [] } = useQuery({
    queryKey: [...CATEGORIES_KEY],
    queryFn: fetchCategories,
  });

  const save = useMutation({
    mutationFn: () => {
      const shared = { remarks, preferences, category_id: categoryId || null };
      if (source) return updateSource(source.id, { ...shared, title });
      return createSource({
        ...shared,
        url,
        title: title.trim() || undefined,
        lookback_days: lookbackDays,
      });
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['blogs'] });
      onDone();
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    save.mutate();
  };

  return (
    <form className="source-form" onSubmit={handleSubmit}>
      {!source && (
        <label>
          Blog or feed URL
          <input
            type="url"
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://blog.example.com"
          />
        </label>
      )}
      <label>
        Title
        <input
          type="text"
          required={Boolean(source)}
          maxLength={500}
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={source ? undefined : 'Defaults to the title of the blog'}
        />
      </label>
      <label>
        Category
        <select value={categoryId} onChange={(e) => setCategoryId(e.target.value)}>
          <option value="">Unfiled</option>
          {categories.map((category) => (
            <option key={category.id} value={category.id}>
              {category.name}
            </option>
          ))}
        </select>
      </label>
      <label>
        Preferences
        <textarea
          rows={2}
          value={preferences}
          onChange={(e) => setPreferences(e.target.value)}
          placeholder="What you want from this blog"
        />
        <span className="source-form-hint">
          {source
            ? 'Changes apply to new posts only.'
            : 'Each post is scored against this. Leave it empty for summaries only.'}
        </span>
      </label>
      <label>
        Remarks
        <textarea rows={2} value={remarks} onChange={(e) => setRemarks(e.target.value)} />
      </label>
      {!source && (
        <label>
          Look back (days)
          <input
            type="number"
            min={0}
            required
            value={lookbackDays}
            onChange={(e) => setLookbackDays(Number(e.target.value))}
          />
          <span className="source-form-hint">
            This can't be changed later. Feeds may only list recent posts, so a look back may
            return fewer posts than expected.
          </span>
        </label>
      )}
      {save.isError && <p className="auth-error">{save.error.message}</p>}
      <div className="source-form-actions">
        <button type="submit" className="btn-secondary" disabled={save.isPending}>
          {save.isPending ? 'Saving…' : source ? 'Save' : 'Add blog'}
        </button>
        {onCancel && (
          <button type="button" className="btn-cancel" onClick={onCancel}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
