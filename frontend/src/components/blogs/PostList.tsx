/**
 * The posts of a view, scrolling without limit.
 *
 * A verdict, or marking a post read, is applied to the cached pages right
 * away. A post that no longer belongs to the view (or to its read filter)
 * leaves the list and an undo stays up for a few seconds.
 * The next page comes from the server's keyset cursor, so posts leaving the
 * list skip nothing.
 */

import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type { InfiniteData } from '@tanstack/react-query';
import {
  fetchPosts,
  MAX_BULK_POSTS,
  setPostRead,
  setPostsState,
  setPostState,
} from '../../api/blogs';
import type { PostFilters } from '../../api/blogs';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';
import type { BlogPost, PostPage, PostState, PostView, Tag } from '../../types';
import ConfirmDialog from '../ConfirmDialog';
import PostCard from './PostCard';

export const UNDO_MS = 6000;

const EMPTY: Record<PostView, string> = {
  all: 'No posts yet.',
  relevant: 'Posts you mark as useful appear here.',
  new: 'Nothing new to triage.',
};

const STATE_LABELS: Record<PostState, string> = {
  new: 'new',
  useful: 'useful',
  not_useful: 'not useful',
};

type Pages = InfiniteData<PostPage, string | undefined>;

/** What was just done to a post that left the list. `post` is as it was before. */
type Undo = { post: BlogPost } & ({ state: PostState } | { read: boolean });

/** Whether a post in this state stays in the view. */
function belongsTo(view: PostView, state: PostState): boolean {
  if (view === 'new') return state === 'new';
  if (view === 'relevant') return state === 'useful';
  return true;
}

/** Whether a post stays under the read filter once marked read or not. */
function matchesRead(filters: PostFilters, read: boolean): boolean {
  return filters.read === undefined || filters.read === read;
}

function undoMessage(undo: Undo): string {
  const label = 'state' in undo ? STATE_LABELS[undo.state] : undo.read ? 'read' : 'to read';
  return `Marked ${label}: ${undo.post.title ?? undo.post.url}`;
}

function mapPosts(pages: Pages, change: (post: BlogPost) => BlogPost | null): Pages {
  return {
    ...pages,
    pages: pages.pages.map((page) => ({
      ...page,
      posts: page.posts.flatMap((post) => change(post) ?? []),
    })),
  };
}

interface PostListProps {
  view: PostView;
  filters: PostFilters;
}

export default function PostList({ view, filters }: PostListProps) {
  const queryClient = useQueryClient();
  const queryKey = ['blogs', 'posts', view, filters];
  const [undo, setUndo] = useState<Undo | null>(null);
  const [confirmingBulk, setConfirmingBulk] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data, isPending, isError, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      queryKey,
      queryFn: ({ pageParam }) => fetchPosts(view, filters, pageParam),
      initialPageParam: undefined as string | undefined,
      getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    });

  const sentinelRef = useInfiniteScroll(() => void fetchNextPage());

  useEffect(() => {
    if (!undo) return;
    const timer = setTimeout(() => setUndo(null), UNDO_MS);
    return () => clearTimeout(timer);
  }, [undo]);

  // The other views changed too, but this one is already right.
  const markOtherViewsStale = () =>
    queryClient.invalidateQueries({
      queryKey: ['blogs', 'posts'],
      refetchType: 'none',
    });

  const verdict = useMutation({
    mutationFn: ({ post, state }: { post: BlogPost; state: PostState }) =>
      setPostState(post.id, state),
    onMutate: async ({ post, state }) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<Pages>(queryKey);
      queryClient.setQueryData<Pages>(queryKey, (pages) =>
        pages &&
        mapPosts(pages, (item) => {
          if (item.id !== post.id) return item;
          return belongsTo(view, state) ? { ...item, state } : null;
        }),
      );
      setError(null);
      setUndo(belongsTo(view, state) ? null : { post, state });
      return { previous };
    },
    onError: (_err, _vars, context) => {
      queryClient.setQueryData(queryKey, context?.previous);
      setUndo(null);
      setError('Could not save that. Please try again.');
    },
    onSuccess: () => void markOtherViewsStale(),
  });

  const markRead = useMutation({
    mutationFn: ({ post, read }: { post: BlogPost; read: boolean }) =>
      setPostRead(post.id, read),
    onMutate: async ({ post, read }) => {
      await queryClient.cancelQueries({ queryKey });
      const previous = queryClient.getQueryData<Pages>(queryKey);
      const stays = matchesRead(filters, read);
      const readAt = read ? new Date().toISOString() : null;
      queryClient.setQueryData<Pages>(queryKey, (pages) =>
        pages &&
        mapPosts(pages, (item) => {
          if (item.id !== post.id) return item;
          return stays ? { ...item, read_at: readAt } : null;
        }),
      );
      setError(null);
      setUndo(stays ? null : { post, read });
      return { previous };
    },
    onError: (_err, _vars, context) => {
      queryClient.setQueryData(queryKey, context?.previous);
      setUndo(null);
      setError('Could not save that. Please try again.');
    },
    onSuccess: (saved) => {
      // Keep the server's read time on a post that stayed.
      queryClient.setQueryData<Pages>(queryKey, (pages) =>
        pages &&
        mapPosts(pages, (item) => (item.id === saved.id ? { ...item, read_at: saved.read_at } : item)),
      );
      void markOtherViewsStale();
    },
  });

  const undoChange = useMutation({
    mutationFn: (change: Undo) =>
      'state' in change
        ? setPostState(change.post.id, change.post.state)
        : setPostRead(change.post.id, change.post.read_at !== null),
    onMutate: () => setUndo(null),
    onError: () => setError('Could not undo that. Please try again.'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['blogs', 'posts'] }),
  });

  const bulk = useMutation({
    mutationFn: async (ids: string[]) => {
      for (let start = 0; start < ids.length; start += MAX_BULK_POSTS) {
        await setPostsState(ids.slice(start, start + MAX_BULK_POSTS), 'not_useful');
      }
    },
    onMutate: () => setError(null),
    onError: () => setError('Could not mark those posts. Please try again.'),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['blogs', 'posts'] }),
  });

  const setTags = (postId: string, tags: Tag[]) => {
    queryClient.setQueryData<Pages>(queryKey, (pages) =>
      pages && mapPosts(pages, (post) => (post.id === postId ? { ...post, tags } : post)),
    );
    void markOtherViewsStale();
  };

  if (isPending) return <p className="search-status">Loading…</p>;
  if (isError) return <p className="search-status auth-error">Could not load the posts.</p>;

  const posts = data.pages.flatMap((page) => page.posts);

  return (
    <>
      {view === 'new' && posts.length > 0 && (
        <button
          type="button"
          className="btn-secondary blogs-bulk"
          disabled={bulk.isPending}
          onClick={() => setConfirmingBulk(true)}
        >
          Mark visible as not useful
        </button>
      )}
      {error && <p className="auth-error">{error}</p>}
      {posts.length === 0 && !undo && (
        <p className="search-status">
          {EMPTY[view]}{' '}
          {view === 'all' && <Link to="/blogs/sources">Add a blog</Link>}
        </p>
      )}
      <ul className="blog-posts">
        {posts.map((post) => (
          <PostCard
            key={post.id}
            post={post}
            onVerdict={(item, state) => verdict.mutate({ post: item, state })}
            onRead={(item, read) => markRead.mutate({ post: item, read })}
            onTagsChanged={setTags}
          />
        ))}
      </ul>
      {hasNextPage && !isFetchingNextPage && <div ref={sentinelRef} aria-hidden="true" />}
      {isFetchingNextPage && <p className="search-status">Loading…</p>}
      {undo && (
        <div className="post-undo" role="status">
          <span>{undoMessage(undo)}</span>
          <button type="button" onClick={() => undoChange.mutate(undo)}>
            Undo
          </button>
        </div>
      )}
      {confirmingBulk && (
        <ConfirmDialog
          message={`Mark the ${posts.length} visible posts as not useful?`}
          confirmLabel="Mark as not useful"
          onConfirm={() => {
            bulk.mutate(posts.map((post) => post.id));
            setConfirmingBulk(false);
          }}
          onCancel={() => setConfirmingBulk(false)}
        />
      )}
    </>
  );
}
