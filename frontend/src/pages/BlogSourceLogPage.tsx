/**
 * `/blogs/sources/:sourceId/log`: the collection history of one source, for
 * troubleshooting. Each run lists what the feed or sitemap had, what the
 * collection made of each entry, and what the model answered for the posts it
 * analyzed. `?run=` picks a run; the newest by default.
 *
 * Runs that listed nothing (0 listed, 0 new) are left out of the history,
 * unless they failed, were interrupted or are still going.
 *
 * Refresh now collects the source in the background and opens its run, which
 * is polled until it finishes, so entries and summaries appear as they come.
 */

import { useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { fetchRun, fetchRuns, fetchSource, refreshSource } from '../api/blogs';
import DesktopHeader from '../components/DesktopHeader';
import MobileTopBar from '../components/MobileTopBar';
import { useLayoutMode } from '../layout/LayoutModeContext';
import { isSafeLink } from '../lib/safeLink';
import type {
  BlogSource,
  CollectionEntry,
  CollectionRun,
  EntryAnalysis,
  EntryVerdict,
  TextSource,
} from '../types';

/** How often an unfinished run is read again. */
export const POLL_MS = 1500;

const VERDICTS: Record<EntryVerdict, string> = {
  new: 'New post',
  stored: 'Already collected',
  too_old: 'Older than the look back',
  over_cap: 'Left for the next run',
  no_date: 'No date: skipped for good',
  unreadable: 'Page unreadable: tried next run',
  robots: 'Blocked by robots.txt',
  invalid: 'No usable link',
  retry: 'Collected earlier, analyzed again',
};

const ANALYSES: Record<EntryAnalysis, string> = {
  processed: 'Summarized',
  too_short: 'Too short to summarize',
  error: 'Analysis failed: tried next run',
  failed: 'Analysis failed: gave up',
};

const TEXT_SOURCES: Record<TextSource, string> = {
  file: 'saved text',
  page: 'the page',
  feed: 'the feed',
};

function isRunning(run: CollectionRun): boolean {
  return run.finished_at === null;
}

function runStatus(run: CollectionRun): string {
  if (run.interrupted) return 'Interrupted';
  if (run.outcome === null) return isRunning(run) ? 'Reading the source…' : 'Not collected';
  if (isRunning(run)) return 'Analyzing posts…';
  if (run.outcome === 'not_modified') return 'Not modified since the last run';
  if (run.outcome === 'failed') return 'Failed';
  return 'Collected';
}

/**
 * A finished run that listed nothing and failed at nothing, like a feed not
 * modified since the last run: it says nothing worth a line in the history.
 */
export function isEmptyRun(run: CollectionRun): boolean {
  return (
    !isRunning(run) &&
    !run.interrupted &&
    run.outcome !== 'failed' &&
    run.entries_found === 0 &&
    (run.verdicts.new ?? 0) === 0
  );
}

function runCounts(run: CollectionRun): string {
  const fresh = run.verdicts.new ?? 0;
  return `${run.entries_found} listed · ${fresh} new`;
}

function formatChars(count: number): string {
  return `${count.toLocaleString()} characters`;
}

function EntryLink({ entry }: { entry: CollectionEntry }) {
  const label = entry.title ?? (entry.url || 'Untitled entry');
  if (!isSafeLink(entry.url)) return <span className="log-entry-title">{label}</span>;
  return (
    <a href={entry.url} target="_blank" rel="noopener noreferrer" className="log-entry-title">
      {label}
    </a>
  );
}

function EntryAnalysisView({ entry, running }: { entry: CollectionEntry; running: boolean }) {
  if (entry.analysis === null) {
    if (entry.verdict === 'new' && running) {
      return <p className="log-entry-pending">Waiting for the model…</p>;
    }
    return null;
  }
  const text =
    entry.text_source && entry.text_chars !== null
      ? ` · text from ${TEXT_SOURCES[entry.text_source]}, ${formatChars(entry.text_chars)}`
      : '';
  return (
    <div className={`log-entry-analysis ${entry.analysis}`}>
      <p className="log-entry-outcome">
        {ANALYSES[entry.analysis]}
        {text}
      </p>
      {entry.error && <p className="log-entry-error">{entry.error}</p>}
      {entry.match_level && (
        <span className={`post-match ${entry.match_level}`}>{entry.match_level} match</span>
      )}
      {entry.summary && <p className="log-entry-summary">{entry.summary}</p>}
      {entry.motivation && <p className="log-entry-motivation">{entry.motivation}</p>}
    </div>
  );
}

function Entry({ entry, running }: { entry: CollectionEntry; running: boolean }) {
  return (
    <li className={`log-entry ${entry.verdict}`}>
      <div className="log-entry-head">
        <EntryLink entry={entry} />
        <span className={`log-verdict ${entry.verdict}`}>{VERDICTS[entry.verdict]}</span>
      </div>
      <div className="log-entry-meta">
        {entry.title && entry.url && <span className="log-entry-url">{entry.url}</span>}
        {entry.published_at && (
          <time dateTime={entry.published_at}>
            {new Date(entry.published_at).toLocaleString()}
          </time>
        )}
        {entry.feed_text_chars !== null && (
          <span>feed text: {formatChars(entry.feed_text_chars)}</span>
        )}
      </div>
      <EntryAnalysisView entry={entry} running={running} />
    </li>
  );
}

function RunDetail({ sourceId, runId }: { sourceId: string; runId: string }) {
  const [hideStored, setHideStored] = useState(false);
  const { data: run, isPending, isError } = useQuery({
    queryKey: ['blogs', 'runs', sourceId, runId],
    queryFn: () => fetchRun(sourceId, runId),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && !isRunning(data) ? false : POLL_MS;
    },
  });

  if (isPending) return <p className="search-status">Loading…</p>;
  if (isError) return <p className="search-status auth-error">Could not load this run.</p>;

  const running = isRunning(run);
  // A stored entry analyzed in this run is a retry worth seeing.
  const entries = hideStored
    ? run.entries.filter((entry) => entry.verdict !== 'stored' || entry.analysis !== null)
    : run.entries;

  return (
    <section className="log-run" aria-label="Run details">
      <h2>
        {new Date(run.started_at).toLocaleString()} · {runStatus(run)}
      </h2>
      {run.error && <p className="auth-error">{run.error}</p>}
      <p className="log-run-summary">
        {runCounts(run)}
        {run.trigger === 'manual' ? ' · refreshed by hand' : ' · by the job'}
      </p>
      {run.entries.length < run.entries_found && (
        <p className="source-form-hint">
          Showing {run.entries.length} of {run.entries_found} entries: posts collected by
          earlier runs are left out first.
        </p>
      )}
      <label className="log-filter">
        <input
          type="checkbox"
          checked={hideStored}
          onChange={(e) => setHideStored(e.target.checked)}
        />
        Hide posts already collected
      </label>
      {run.entries.length === 0 && (
        <p className="search-status">
          {running ? 'Reading the source…' : 'The source listed nothing.'}
        </p>
      )}
      <ul className="log-entries">
        {entries.map((entry) => (
          <Entry key={entry.id} entry={entry} running={running} />
        ))}
      </ul>
    </section>
  );
}

function RunList({
  runs,
  selected,
  onSelect,
}: {
  runs: CollectionRun[];
  selected: string | undefined;
  onSelect: (runId: string) => void;
}) {
  return (
    <nav className="log-runs" aria-label="Runs">
      <ul>
        {runs.map((run) => (
          <li key={run.id}>
            <button
              type="button"
              className={`log-run-link${run.id === selected ? ' active' : ''}`}
              aria-current={run.id === selected ? 'true' : undefined}
              onClick={() => onSelect(run.id)}
            >
              <span>{new Date(run.started_at).toLocaleString()}</span>
              <span className={`log-run-status ${run.outcome ?? 'running'}`}>
                {runStatus(run)}
              </span>
              <span className="log-run-counts">
                {runCounts(run)}
                {run.trigger === 'manual' && ' · manual'}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function SourceSummary({ source }: { source: BlogSource }) {
  return (
    <div className="log-source">
      <h1>{source.title}</h1>
      <p className="log-entry-url">{source.feed_url}</p>
      <p className="source-form-hint">
        {source.kind === 'sitemap' ? 'Sitemap' : 'Feed'} · collects posts since{' '}
        {new Date(source.collect_since).toLocaleDateString()}
        {source.enabled ? '' : ' · paused'}
      </p>
      <p className="source-form-hint">
        Preferences: {source.preferences ?? 'none, so posts get no match level'}
      </p>
    </div>
  );
}

export default function BlogSourceLogPage() {
  const mode = useLayoutMode();
  const isMobile = mode === 'mobile';
  const { sourceId = '' } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();

  const source = useQuery({
    queryKey: ['blogs', 'sources', sourceId],
    queryFn: () => fetchSource(sourceId),
  });
  const runs = useQuery({
    queryKey: ['blogs', 'runs', sourceId],
    queryFn: () => fetchRuns(sourceId),
    refetchInterval: (query) =>
      query.state.data?.some(isRunning) ? POLL_MS : false,
  });

  const select = (runId: string) => {
    const next = new URLSearchParams(searchParams);
    next.set('run', runId);
    setSearchParams(next, { replace: true });
  };

  const refresh = useMutation({
    mutationFn: () => refreshSource(sourceId),
    onSuccess: (run) => {
      void queryClient.invalidateQueries({ queryKey: ['blogs', 'runs', sourceId] });
      // New posts and the source's last collection change too.
      void queryClient.invalidateQueries({ queryKey: ['blogs', 'posts'] });
      select(run.id);
    },
  });

  const all = runs.data ?? [];
  const requested = searchParams.get('run');
  // The run asked for stays listed, so a refresh that finds nothing does not
  // vanish while it is open.
  const list = all.filter((run) => run.id === requested || !isEmptyRun(run));
  const selected = requested ?? list[0]?.id;
  const busy = refresh.isPending || all.some(isRunning);

  return (
    <div className="app-shell" data-layout={mode}>
      {isMobile ? (
        <MobileTopBar title="History" backTo="/blogs/sources" />
      ) : (
        <DesktopHeader />
      )}
      <main className="blog-sources-page blog-log-page">
        {!isMobile && (
          <p>
            <Link to="/blogs/sources">&larr; Back to sources</Link>
          </p>
        )}
        {source.isError && <p className="auth-error">Could not load this blog.</p>}
        {source.data && <SourceSummary source={source.data} />}
        <div className="log-actions">
          <button
            type="button"
            className="btn-secondary"
            disabled={busy || source.data?.enabled === false}
            onClick={() => refresh.mutate()}
          >
            {busy ? 'Collecting…' : 'Refresh now'}
          </button>
          {refresh.isError && <p className="auth-error">{refresh.error.message}</p>}
        </div>
        {runs.isSuccess && all.length === 0 && (
          <p className="empty">No collection yet. The job or Refresh now will log one here.</p>
        )}
        {all.length > 0 && list.length === 0 && (
          <p className="empty">No recent run listed anything.</p>
        )}
        {list.length > 0 && (
          <div className="log-layout">
            <RunList runs={list} selected={selected} onSelect={select} />
            {selected && <RunDetail key={selected} sourceId={sourceId} runId={selected} />}
          </div>
        )}
      </main>
    </div>
  );
}
