import type { Block, BlockNoteEditor } from '@blocknote/core';
import type { ServerRegistry } from '../markdown/serverRegistry';

interface DebugBlockViewProps {
  blocks: Block[];
  editor: BlockNoteEditor;
  registry: ServerRegistry;
}

export default function DebugBlockView({ blocks, editor, registry }: DebugBlockViewProps) {
  return (
    <div className="debug-panel">
      <div className="debug-panel-header">Block structure ({blocks.length} blocks)</div>
      <div className="debug-block-list">
        {blocks.map((block, i) => {
          const state = registry.get(block.id);
          const serialized = editor.blocksToMarkdownLossy([block]).trim();
          return (
            <div key={block.id}>
              {i > 0 && (
                <div className="debug-connector">
                  <div className="debug-connector-line" />
                  <div className="debug-connector-label">↓</div>
                  <div className="debug-connector-line" />
                </div>
              )}
              <div className={`debug-block ${state ? 'debug-block-synced' : 'debug-block-new'}`}>
                <div className="debug-block-header">
                  <span className="debug-block-index">#{i}</span>
                  <span className="debug-block-type">{block.type}</span>
                  <span className={`debug-block-badge ${state ? 'synced' : 'new'}`}>
                    {state ? 'server' : 'new'}
                  </span>
                </div>
                <div className="debug-block-content">{serialized || <em>(empty)</em>}</div>
                <div className="debug-block-id">
                  bn: {block.id.slice(0, 8)}…
                  {state && (
                    <>
                      {' '} | node: {state.nodeId.slice(0, 8)}… v{state.version}
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
