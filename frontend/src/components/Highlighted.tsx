/** Search-result text from API segments: matches as `<mark>`, always as text (never HTML). */

import type { SnippetSegment } from '../types';

export default function Highlighted({ segments }: { segments: SnippetSegment[] }) {
  return (
    <>
      {segments.map((segment, i) =>
        segment.highlighted ? <mark key={i}>{segment.text}</mark> : <span key={i}>{segment.text}</span>,
      )}
    </>
  );
}
