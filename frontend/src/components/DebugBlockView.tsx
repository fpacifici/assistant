import type { MarkdownBlockType } from '../types';

export interface DebugBlockSnapshot {
  index: number;
  blockType: MarkdownBlockType;
  content: string;
  lineStart: number;
  lineCount: number;
  dirty: boolean;
  hasServerState: boolean;
  nodeId: string | null;
  version: number | null;
  isCurrent: boolean;
}

interface DebugBlockViewProps {
  blocks: DebugBlockSnapshot[];
}

export default function DebugBlockView({ blocks }: DebugBlockViewProps) {
  return (
    <div className="debug-panel">
      <div className="debug-panel-header">
        Block List ({blocks.length} blocks)
      </div>
      <div className="debug-block-list">
        {blocks.map((block, i) => (
          <div key={i}>
            <div
              className={`debug-block${block.isCurrent ? ' debug-block-current' : ''}${block.dirty ? ' debug-block-dirty' : ''}`}
            >
              <div className="debug-block-header">
                <span className="debug-block-type">{block.blockType}</span>
                <span className="debug-block-line">L{block.lineStart}</span>
                {block.dirty && <span className="debug-block-badge dirty">dirty</span>}
                {block.hasServerState && (
                  <span className="debug-block-badge synced">v{block.version}</span>
                )}
              </div>
              <div className="debug-block-content">
                {block.content.length > 80
                  ? block.content.slice(0, 80) + '…'
                  : block.content || '(empty)'}
              </div>
              {block.nodeId && (
                <div className="debug-block-id">{block.nodeId.slice(0, 8)}…</div>
              )}
            </div>
            {i < blocks.length - 1 && (
              <div className="debug-connector">
                <div className="debug-connector-line" />
                <span className="debug-connector-label">↕</span>
                <div className="debug-connector-line" />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
