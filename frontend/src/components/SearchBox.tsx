/** Search input: submitting opens the search page (`/search?q=…`). */

import { useState } from 'react';
import { useNavigate } from 'react-router';

interface SearchBoxProps {
  initialQuery?: string;
  autoFocus?: boolean;
}

export default function SearchBox({ initialQuery = '', autoFocus = false }: SearchBoxProps) {
  const navigate = useNavigate();
  const [query, setQuery] = useState(initialQuery);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;
    navigate(`/search?${new URLSearchParams({ q: query })}`);
  };

  return (
    <form role="search" className="search-box" onSubmit={handleSubmit}>
      <input
        type="search"
        aria-label="Search notes"
        placeholder='Search notes — words, "phrases", tag:name'
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        autoFocus={autoFocus}
        enterKeyHint="search"
      />
    </form>
  );
}
