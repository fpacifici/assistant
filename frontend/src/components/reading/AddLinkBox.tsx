/**
 * Saves a link, with the user's notes on it if they wrote any. It appears at
 * once, being analyzed, and fills in when done.
 * A link already saved, in any state, is refused, and the box links to it.
 */

import { useState } from 'react';
import { Link } from 'react-router';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../../api/client';
import { addLink, fetchLink, linkLocation, READING_KEY } from '../../api/reading';
import { linkTitle } from '../../lib/readingLinks';
import type { ReadingLink } from '../../types';

class DuplicateLink extends Error {
  constructor(public link: ReadingLink) {
    super('This link is already in your reading list');
  }
}

/** Save the URL; on a duplicate, load the link already saved. */
async function save(url: string, notes: string): Promise<ReadingLink> {
  try {
    return await addLink(url, notes);
  } catch (err) {
    const existing = err instanceof ApiError && err.status === 409 ? err.body.link_id : null;
    if (typeof existing !== 'string') throw err;
    throw new DuplicateLink(await fetchLink(existing));
  }
}

export default function AddLinkBox() {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState('');
  const [notes, setNotes] = useState('');
  const add = useMutation({
    mutationFn: () => save(url.trim(), notes),
    onSuccess: () => {
      setUrl('');
      setNotes('');
      return queryClient.invalidateQueries({ queryKey: [...READING_KEY] });
    },
  });

  return (
    <form
      className="add-link"
      aria-label="Add link"
      onSubmit={(e) => {
        e.preventDefault();
        add.mutate();
      }}
    >
      <input
        type="url"
        required
        aria-label="Link to add"
        placeholder="https://… a page, PDF or video to read later"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
      />
      <button type="submit" className="btn-secondary" disabled={!url.trim() || add.isPending}>
        {add.isPending ? 'Adding…' : 'Add link'}
      </button>
      <textarea
        aria-label="Notes on the link"
        placeholder="Your notes (optional): why you saved it, what to look for"
        rows={notes ? 2 : 1}
        maxLength={10000}
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
      />
      {add.error instanceof DuplicateLink ? (
        <p className="auth-error">
          {add.error.message}:{' '}
          <Link to={linkLocation(add.error.link)}>{linkTitle(add.error.link)}</Link>
        </p>
      ) : (
        add.isError && <p className="auth-error">{add.error.message}</p>
      )}
    </form>
  );
}
