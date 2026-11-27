/** Polls an open note for other people's edits and who else is on it. */

import { useCallback, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchLiveNote } from '../api/presence';
import type { ActiveUser, LiveNote, NoteNode } from '../types';

/** How often an open, visible note asks for changes. */
export const LIVE_POLL_MS = 2_000;

const NO_USERS: ActiveUser[] = [];

interface Poll {
  live: LiveNote;
  /** `saveEpoch` when the request was sent. */
  epoch: number;
}

export interface LiveNoteOptions {
  /**
   * Bumped by the editor when a save starts and when it ends. Nodes from a
   * request that overlapped a save are dropped: they may predate blocks
   * the save just created, which would then look deleted.
   */
  saveEpoch: React.RefObject<number>;
  /** Merge the note's current nodes into the editor. */
  onNodes: (nodes: NoteNode[]) => void;
  /** The note's title changed (by anyone). */
  onTitle: (title: string) => void;
}

/**
 * While the note is open, poll `GET .../live` every `LIVE_POLL_MS` (React
 * Query pauses it while the page is hidden). The server sends the nodes only
 * when the note changed since the last revision merged here.
 *
 * Returns the other users on the note and `pollNow`, to ask right away (after
 * a save conflict, say).
 */
export function useLiveNote(
  notebookId: string | undefined,
  noteId: string | undefined,
  { saveEpoch, onNodes, onTitle }: LiveNoteOptions,
): { presence: ActiveUser[]; pollNow: () => void; reset: () => void } {
  // The revision whose nodes are in the editor; null to get them.
  const revision = useRef<string | null>(null);
  const callbacks = useRef({ onNodes, onTitle });
  useEffect(() => {
    callbacks.current = { onNodes, onTitle };
  });

  const { data, refetch } = useQuery({
    queryKey: ['live', notebookId, noteId],
    queryFn: async (): Promise<Poll> => {
      const epoch = saveEpoch.current;
      const live = await fetchLiveNote(notebookId!, noteId!, revision.current);
      return { live, epoch };
    },
    enabled: !!notebookId && !!noteId,
    refetchInterval: LIVE_POLL_MS,
    // Each poll is new information; never serve an old one.
    gcTime: 0,
    staleTime: 0,
  });

  const lastTitle = useRef<string | null>(null);
  useEffect(() => {
    if (!data) return;
    const { live, epoch } = data;
    if (lastTitle.current !== null && lastTitle.current !== live.title) {
      callbacks.current.onTitle(live.title);
    }
    lastTitle.current = live.title;
    if (!live.nodes) return;
    // Saving, or saved meanwhile: ask again on the next poll.
    if (epoch !== saveEpoch.current || saveEpoch.current % 2 === 1) return;
    callbacks.current.onNodes(live.nodes);
    revision.current = live.revision;
  }, [data, saveEpoch]);

  const reset = useCallback(() => {
    revision.current = null;
    lastTitle.current = null;
  }, []);

  useEffect(reset, [noteId, reset]);

  const pollNow = useCallback(() => {
    void refetch();
  }, [refetch]);

  return { presence: data?.live.presence ?? NO_USERS, pollNow, reset };
}
