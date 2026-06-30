import type { NoteNode } from '../types';

interface Props {
  nodes: NoteNode[];
}

function parsePayload(payload: string): { name: string; url: string } | null {
  const match = payload.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
  if (!match) return null;
  return { name: match[1], url: match[2] };
}

export default function AttachmentList({ nodes }: Props) {
  if (nodes.length === 0) return null;

  return (
    <div className="attachment-list">
      <span className="attachment-list-label">Attachments</span>
      <ul>
        {nodes.map((node) => {
          const parsed = node.payload ? parsePayload(node.payload) : null;
          if (!parsed) return null;
          return (
            <li key={node.id}>
              <a href={parsed.url} download={parsed.name}>
                {parsed.name}
              </a>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
