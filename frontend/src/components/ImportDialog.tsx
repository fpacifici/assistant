/**
 * Modal for importing an Evernote HTML export: pick a zip, upload it, run the
 * import, then show the report. Notes the user edited since an earlier import
 * are left alone by the server and listed here with links.
 */

import { useState } from 'react';
import { Link } from 'react-router';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError } from '../api/client';
import { runImport, uploadImportZip } from '../api/imports';
import type { ImportReport, KeptNote } from '../api/imports';

type Phase =
  | { kind: 'select' }
  | { kind: 'uploading'; progress: number }
  | { kind: 'importing' }
  | { kind: 'done'; report: ImportReport };

interface ImportDialogProps {
  onClose: () => void;
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : '';
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
}

function KeptNoteList({ notes, onNavigate }: { notes: KeptNote[]; onNavigate: () => void }) {
  return (
    <ul className="import-report-list">
      {notes.map((note) => (
        <li key={note.note_id}>
          <Link
            to={`/notebooks/${note.notebook_id}/notes/${note.note_id}`}
            onClick={onNavigate}
          >
            {note.title}
          </Link>{' '}
          <span className="import-report-meta">
            in {note.notebook}
            {note.imported_at && <> · imported {formatDate(note.imported_at)}</>}
            {' '}· edited {formatDate(note.modified_at)}
          </span>
        </li>
      ))}
    </ul>
  );
}

function ReportView({ report, onClose }: { report: ImportReport; onClose: () => void }) {
  const counts = [
    [report.created, 'created'],
    [report.refreshed, 'updated'],
    [report.unchanged, 'unchanged'],
  ] as const;

  return (
    <div className="import-report">
      <p className="import-report-summary">
        {counts.map(([n, label]) => `${plural(n, 'note')} ${label}`).join(', ')}
        {report.skipped_web_clip > 0 &&
          `, ${plural(report.skipped_web_clip, 'web clip')} skipped`}
        .
      </p>

      {report.kept_modified.length > 0 && (
        <section>
          <h4>Not updated because you edited them</h4>
          <KeptNoteList notes={report.kept_modified} onNavigate={onClose} />
        </section>
      )}

      {report.kept_untracked.length > 0 && (
        <section>
          <h4>Imported before import tracking, not updated</h4>
          <KeptNoteList notes={report.kept_untracked} onNavigate={onClose} />
        </section>
      )}

      {report.duplicate_title.length > 0 && (
        <section>
          <h4>Not imported: another note in the notebook has the same title</h4>
          <ul className="import-report-list">
            {report.duplicate_title.map((dup) => (
              <li key={dup.source_path}>{dup.source_path}</li>
            ))}
          </ul>
        </section>
      )}

      {report.notebooks_failed.length > 0 && (
        <section>
          <h4>Notebooks skipped</h4>
          <ul className="import-report-list">
            {report.notebooks_failed.map((nb) => (
              <li key={nb.name}>
                {nb.name}{' '}
                <span className="import-report-meta">
                  {nb.reason} ({plural(nb.skipped_notes, 'note')} not imported)
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.failed.length > 0 && (
        <section>
          <h4>Failed</h4>
          <ul className="import-report-list">
            {report.failed.map((f) => (
              <li key={f.source_path}>
                {f.source_path} <span className="import-report-meta">{f.error}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="confirm-actions">
        <button onClick={onClose}>Done</button>
      </div>
    </div>
  );
}

export default function ImportDialog({ onClose }: ImportDialogProps) {
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [includeWebClips, setIncludeWebClips] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: 'select' });
  const [error, setError] = useState<string | null>(null);

  const busy = phase.kind === 'uploading' || phase.kind === 'importing';
  const close = () => {
    if (!busy) onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;
    setError(null);
    setPhase({ kind: 'uploading', progress: 0 });
    try {
      const importId = await uploadImportZip(file, (progress) =>
        setPhase({ kind: 'uploading', progress }),
      );
      setPhase({ kind: 'importing' });
      const report = await runImport(importId, { includeWebClips });
      setPhase({ kind: 'done', report });
      queryClient.invalidateQueries({ queryKey: ['notebooks'] });
      queryClient.invalidateQueries({ queryKey: ['notes'] });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Import failed');
      setPhase({ kind: 'select' });
    }
  };

  return (
    <div className="modal-overlay" onClick={close}>
      <div
        className="modal import-dialog"
        role="dialog"
        aria-modal="true"
        aria-label="Import from Evernote"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h3>Import from Evernote</h3>
          <button className="modal-close" onClick={close} aria-label="Close" disabled={busy}>
            &times;
          </button>
        </div>

        {phase.kind === 'select' && (
          <form onSubmit={handleSubmit} className="import-form">
            <p className="import-help">
              Upload a zip of your Evernote HTML export: one folder per notebook, one
              .html file per note. Importing the same export again updates notes you
              have not edited since.
            </p>
            <label>
              Export zip
              <input
                type="file"
                accept=".zip,application/zip"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
            <label className="import-checkbox">
              <input
                type="checkbox"
                checked={includeWebClips}
                onChange={(e) => setIncludeWebClips(e.target.checked)}
              />
              Include web clips
            </label>
            {error && <p className="share-error">{error}</p>}
            <div className="confirm-actions">
              <button type="button" className="btn-cancel" onClick={onClose}>
                Cancel
              </button>
              <button type="submit" disabled={!file}>
                Import
              </button>
            </div>
          </form>
        )}

        {phase.kind === 'uploading' && (
          <div className="import-progress">
            <progress value={phase.progress} max={1} />
            <p>Uploading… {Math.round(phase.progress * 100)}%</p>
          </div>
        )}

        {phase.kind === 'importing' && (
          <div className="import-progress">
            <p>Importing notes… this can take a few minutes for a large export.</p>
          </div>
        )}

        {phase.kind === 'done' && <ReportView report={phase.report} onClose={onClose} />}
      </div>
    </div>
  );
}
