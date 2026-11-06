/**
 * One post. The title opens the original post in a new tab: there is no
 * embedded reader, and opening a post doesn't change its state. Everything on
 * the card that came from a feed or the model is rendered as text.
 */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { addPostTag, removePostTag } from '../../api/blogs';
import { isSafeLink } from '../../lib/safeLink';
import type { BlogPost, PostState, Tag } from '../../types';
import TagChips from '../TagChips';
import type { TagChoice } from '../TagChips';

interface PostCardProps {
  post: BlogPost;
  onVerdict: (post: BlogPost, state: PostState) => void;
  onTagsChanged: (postId: string, tags: Tag[]) => void;
}

function PostTitle({ post }: { post: BlogPost }) {
  const title = post.title ?? post.url;
  if (!isSafeLink(post.url)) return <span className="post-card-title plain">{title}</span>;
  return (
    <a href={post.url} target="_blank" rel="noopener noreferrer" className="post-card-title">
      {title}
    </a>
  );
}

export default function PostCard({ post, onVerdict, onTagsChanged }: PostCardProps) {
  const queryClient = useQueryClient();
  const [tagError, setTagError] = useState<string | null>(null);
  const failed = (err: Error) => setTagError(err.message);

  const addTag = useMutation({
    mutationFn: (tag: TagChoice) => addPostTag(post.id, tag),
    onSuccess: (tags, tag) => {
      onTagsChanged(post.id, tags);
      if ('name' in tag) void queryClient.invalidateQueries({ queryKey: ['tags'] });
      setTagError(null);
    },
    onError: failed,
  });

  const removeTag = useMutation({
    mutationFn: (tagId: string) => removePostTag(post.id, tagId),
    onSuccess: (_, tagId) => {
      onTagsChanged(post.id, post.tags.filter((tag) => tag.id !== tagId));
      setTagError(null);
    },
    onError: failed,
  });

  const verdictButton = (state: PostState, label: string) => (
    <button
      type="button"
      className="btn-secondary"
      aria-pressed={post.state === state}
      onClick={() => onVerdict(post, post.state === state ? 'new' : state)}
    >
      {label}
    </button>
  );

  return (
    <li className="post-card">
      <PostTitle post={post} />
      <div className="post-card-meta">
        <span>{post.source_title}</span>
        <time dateTime={post.published_at}>
          {new Date(post.published_at).toLocaleDateString()}
        </time>
        {post.match_level && (
          <span className={`post-match ${post.match_level}`}>{post.match_level} match</span>
        )}
      </div>
      {post.summary ? (
        <p className="post-card-summary">{post.summary}</p>
      ) : (
        <p className="post-card-summary unavailable">Summary unavailable</p>
      )}
      {post.motivation && <p className="post-card-motivation">{post.motivation}</p>}
      <div className="post-card-footer">
        <TagChips
          tags={post.tags}
          onAdd={(tag) => addTag.mutate(tag)}
          onRemove={(tagId) => removeTag.mutate(tagId)}
          error={tagError}
        />
        <div className="post-verdict" role="group" aria-label="Verdict">
          {verdictButton('useful', 'Useful')}
          {verdictButton('not_useful', 'Not useful')}
        </div>
      </div>
    </li>
  );
}
