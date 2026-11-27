/** The blocks someone else changed while they had unsaved edits here. */

import type { BlockConflict } from '../../markdown/liveMerge';

/**
 * One row per conflicted block and the two ways out. The blocks themselves
 * are outlined by the editor (`conflictStyle`). Nodes don't record who
 * last edited them, so the other person is not named.
 */
export default function ConflictBar({
  conflicts,
  onShow,
  onKeepMine,
  onUseTheirs,
}: {
  conflicts: ReadonlyMap<string, BlockConflict>;
  onShow: (blockId: string) => void;
  onKeepMine: (blockId: string) => void;
  onUseTheirs: (blockId: string) => void;
}) {
  if (conflicts.size === 0) return null;
  return (
    <div className="conflict-bar" role="alert">
      {[...conflicts].map(([blockId, conflict]) => {
        const what =
          conflict.payload === null
            ? 'Someone else deleted a block you are editing.'
            : 'Someone else changed a block you are editing.';
        return (
          <div key={blockId} className="conflict-row">
            <button type="button" className="conflict-show" onClick={() => onShow(blockId)}>
              {what}
            </button>
            <button type="button" onClick={() => onKeepMine(blockId)}>
              Keep mine
            </button>
            <button type="button" onClick={() => onUseTheirs(blockId)}>
              {conflict.payload === null ? 'Delete it' : 'Use theirs'}
            </button>
          </div>
        );
      })}
    </div>
  );
}
