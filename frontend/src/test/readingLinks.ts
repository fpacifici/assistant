import type { ReadingLink } from '../types';

/** A reading link to read, analyzed, with a title and a summary. */
export function readingLink(fields: Partial<ReadingLink> = {}): ReadingLink {
  return {
    id: 'l1',
    url: 'https://www.example.com/btrees',
    title: 'On B-trees',
    link_type: 'web',
    category_id: null,
    summary: 'B-trees keep data sorted.',
    user_notes: null,
    analysis_status: 'done',
    last_error: null,
    state: 'to_read',
    note_id: null,
    note_notebook_id: null,
    created_at: '2026-11-01T10:00:00Z',
    decided_at: null,
    ...fields,
  };
}
