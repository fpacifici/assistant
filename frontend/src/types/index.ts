export interface User {
  uid: string;
  email: string;
  firstname: string;
  lastname: string;
  invite_quota_remaining: number;
  auth_provider: 'password' | 'google';
}

export interface Invite {
  id: string;
  invitee_email: string;
  state: 'pending' | 'void' | 'converted';
  created_at: string;
  expires_at: string;
  email_sent?: boolean;
}

export interface InvitesConfigFlags {
  registration_enabled: boolean;
  invites_enabled: boolean;
}

export interface Notebook {
  id: string;
  name: string;
  owner_id: string;
  permissions: string[];
}

export interface Tag {
  id: string;
  name: string;
}

export interface Note {
  id: string;
  notebook_id: string;
  owner_id: string;
  title: string;
  creation_timestamp: string;
  update_timestamp: string;
  permissions: string[];
  /** The caller's own tags on this note. */
  tags: Tag[];
  /** Plain-text excerpt of the note's first blocks ("" when empty). */
  preview: string;
}

export interface Entitlement {
  id: string;
  principal_id: string;
  principal_email: string;
  role: string;
  created_at: string;
}

export interface NoteNode {
  id: string;
  note_id: string;
  author_id: string;
  node_type: string;
  payload: string | null;
  block_type: string | null;
  version: number;
  update_timestamp: string;
}

/** A run of search-result text; `highlighted` when it matched the query. */
export interface SnippetSegment {
  text: string;
  highlighted: boolean;
}

/** A matching block of a note; open the note at `node_id`. */
export interface SearchSnippet {
  node_id: string;
  segments: SnippetSegment[];
}

export interface SearchResult {
  note: Note;
  notebook: { id: string; name: string };
  score: number;
  /** The note title with matched words highlighted. */
  title: SnippetSegment[];
  snippets: SearchSnippet[];
}

export interface SearchResponse {
  results: SearchResult[];
  /** `tag:` filters naming a tag the caller doesn't have. */
  unknown_tags: string[];
  offset: number;
  limit: number;
}

export interface BlogDirectory {
  id: string;
  name: string;
  created_at: string;
}

export interface BlogSource {
  id: string;
  directory_id: string | null;
  url: string;
  feed_url: string;
  kind: 'feed' | 'sitemap';
  title: string;
  remarks: string | null;
  preferences: string | null;
  collect_since: string;
  enabled: boolean;
  archived_at: string | null;
  last_fetched_at: string | null;
  last_error: string | null;
  consecutive_failures: number;
  created_at: string;
  /** Only set when a single source is read. */
  useful_post_count: number | null;
}

export type PostState = 'new' | 'useful' | 'not_useful';
export type MatchLevel = 'high' | 'medium' | 'low';
/** `new` is the Triage view: posts not evaluated yet. */
export type PostView = 'all' | 'relevant' | 'new';

export interface BlogPost {
  id: string;
  source_id: string;
  source_title: string;
  url: string;
  /** Null for a failed post nothing could name. */
  title: string | null;
  published_at: string;
  /** Null for a failed post. */
  summary: string | null;
  match_level: MatchLevel | null;
  motivation: string | null;
  status: 'processed' | 'failed';
  state: PostState;
  evaluated_at: string | null;
  /** When the user marked it read; null while it is still to read. */
  read_at: string | null;
  tags: Tag[];
}

export type RunTrigger = 'job' | 'manual';
export type RunOutcome = 'collected' | 'not_modified' | 'failed';
export type EntryVerdict =
  | 'new'
  | 'stored'
  | 'too_old'
  | 'over_cap'
  | 'no_date'
  | 'unreadable'
  | 'robots'
  | 'invalid'
  | 'retry';
export type EntryAnalysis = 'processed' | 'too_short' | 'error' | 'failed';
export type TextSource = 'file' | 'page' | 'feed';

/** A run of the collection log: one source, read by the job or a refresh. */
export interface CollectionRun {
  id: string;
  source_id: string;
  trigger: RunTrigger;
  started_at: string;
  /** Null while its posts are still being analyzed. */
  finished_at: string | null;
  /** Null while the source is still being read. */
  outcome: RunOutcome | null;
  error: string | null;
  interrupted: boolean;
  /** Every entry the source listed; the log may keep fewer. */
  entries_found: number;
  /** Logged entries by verdict. */
  verdicts: Partial<Record<EntryVerdict, number>>;
}

/** What the source listed in a run and what became of it. */
export interface CollectionEntry {
  id: string;
  /** Empty for an entry with no link. */
  url: string;
  title: string | null;
  published_at: string | null;
  verdict: EntryVerdict;
  post_id: string | null;
  feed_text_chars: number | null;
  /** Null when the run did not analyze it. */
  analysis: EntryAnalysis | null;
  text_source: TextSource | null;
  text_chars: number | null;
  error: string | null;
  summary: string | null;
  match_level: MatchLevel | null;
  motivation: string | null;
  analyzed_at: string | null;
}

export interface CollectionRunDetail extends CollectionRun {
  entries: CollectionEntry[];
}

export interface PostPage {
  posts: BlogPost[];
  next_cursor: string | null;
}
