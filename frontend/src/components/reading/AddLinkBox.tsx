/** Saves a link. It appears at once, being analyzed, and fills in when done. */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { addLink, READING_KEY } from '../../api/reading';

export default function AddLinkBox() {
  const queryClient = useQueryClient();
  const [url, setUrl] = useState('');
  const add = useMutation({
    mutationFn: () => addLink(url.trim()),
    onSuccess: () => {
      setUrl('');
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
      {add.isError && <p className="auth-error">{add.error.message}</p>}
    </form>
  );
}
