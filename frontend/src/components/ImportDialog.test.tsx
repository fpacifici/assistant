import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ImportDialog from './ImportDialog';
import { renderWithProviders } from '../test/renderWithProviders';
import { ApiError } from '../api/client';
import type { ImportReport } from '../api/imports';

vi.mock('../api/imports', () => ({
  uploadImportZip: vi.fn(),
  runImport: vi.fn(),
}));

import { runImport, uploadImportZip } from '../api/imports';

const mockUpload = vi.mocked(uploadImportZip);
const mockRun = vi.mocked(runImport);

function emptyReport(overrides: Partial<ImportReport> = {}): ImportReport {
  return {
    notebooks_touched: 0,
    created: 0,
    refreshed: 0,
    unchanged: 0,
    skipped_web_clip: 0,
    imported_web_clip: 0,
    kept_modified: [],
    kept_untracked: [],
    duplicate_title: [],
    failed: [],
    notebooks_failed: [],
    ...overrides,
  };
}

const zip = () => new File(['data'], 'export.zip', { type: 'application/zip' });

async function chooseFileAndImport(user: ReturnType<typeof userEvent.setup>) {
  await user.upload(screen.getByLabelText('Export zip'), zip());
  await user.click(screen.getByRole('button', { name: 'Import' }));
}

describe('ImportDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('disables Import until a file is chosen', async () => {
    const user = userEvent.setup();
    renderWithProviders(<ImportDialog onClose={() => {}} />);

    expect(screen.getByRole('button', { name: 'Import' })).toBeDisabled();
    await user.upload(screen.getByLabelText('Export zip'), zip());
    expect(screen.getByRole('button', { name: 'Import' })).toBeEnabled();
  });

  it('uploads, runs the import and shows the counts', async () => {
    const user = userEvent.setup();
    mockUpload.mockResolvedValue('imp-1');
    mockRun.mockResolvedValue(emptyReport({ created: 3, refreshed: 1, unchanged: 2 }));
    renderWithProviders(<ImportDialog onClose={() => {}} />);

    await user.click(screen.getByLabelText('Include web clips'));
    await chooseFileAndImport(user);

    expect(
      await screen.findByText('3 notes created, 1 note updated, 2 notes unchanged.'),
    ).toBeInTheDocument();
    expect(mockUpload).toHaveBeenCalledWith(expect.any(File), expect.any(Function));
    expect(mockRun).toHaveBeenCalledWith('imp-1', { includeWebClips: true });
  });

  it('lists notes kept because they were edited, with links', async () => {
    const user = userEvent.setup();
    mockUpload.mockResolvedValue('imp-1');
    mockRun.mockResolvedValue(
      emptyReport({
        unchanged: 4,
        kept_modified: [
          {
            note_id: 'note-1',
            notebook_id: 'nb-1',
            title: 'Groceries',
            notebook: 'Personal',
            source_path: 'Personal/Groceries.html',
            imported_at: '2026-09-01T10:00:00Z',
            modified_at: '2026-09-02T10:00:00Z',
          },
        ],
      }),
    );
    renderWithProviders(<ImportDialog onClose={() => {}} />);

    await chooseFileAndImport(user);

    const heading = await screen.findByText('Not updated because you edited them');
    const section = heading.closest('section')!;
    const link = within(section).getByRole('link', { name: 'Groceries' });
    expect(link).toHaveAttribute('href', '/notebooks/nb-1/notes/note-1');
    expect(within(section).getByText(/in Personal/)).toBeInTheDocument();
  });

  it('hides empty report sections', async () => {
    const user = userEvent.setup();
    mockUpload.mockResolvedValue('imp-1');
    mockRun.mockResolvedValue(emptyReport({ created: 1 }));
    renderWithProviders(<ImportDialog onClose={() => {}} />);

    await chooseFileAndImport(user);

    await screen.findByText(/1 note created/);
    expect(screen.queryByText('Not updated because you edited them')).not.toBeInTheDocument();
    expect(screen.queryByText('Failed')).not.toBeInTheDocument();
    expect(screen.queryByText('Notebooks skipped')).not.toBeInTheDocument();
  });

  it('shows duplicates, skipped notebooks and failures', async () => {
    const user = userEvent.setup();
    mockUpload.mockResolvedValue('imp-1');
    mockRun.mockResolvedValue(
      emptyReport({
        duplicate_title: [{ title: 'Untitled', notebook: 'NB', source_path: 'NB/Untitled (1).html' }],
        notebooks_failed: [{ name: 'Shared', reason: 'Owned by another user', skipped_notes: 2 }],
        failed: [{ source_path: 'NB/bad.html', error: 'boom' }],
      }),
    );
    renderWithProviders(<ImportDialog onClose={() => {}} />);

    await chooseFileAndImport(user);

    expect(await screen.findByText('NB/Untitled (1).html')).toBeInTheDocument();
    expect(screen.getByText(/Owned by another user \(2 notes not imported\)/)).toBeInTheDocument();
    expect(screen.getByText('NB/bad.html')).toBeInTheDocument();
  });

  it('shows the error and lets the user retry when the upload fails', async () => {
    const user = userEvent.setup();
    mockUpload.mockRejectedValue(new ApiError(400, 'The uploaded file is not a zip archive'));
    renderWithProviders(<ImportDialog onClose={() => {}} />);

    await chooseFileAndImport(user);

    expect(
      await screen.findByText('The uploaded file is not a zip archive'),
    ).toBeInTheDocument();
    expect(mockRun).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Import' })).toBeInTheDocument();
  });

  it('shows progress while uploading and cannot be closed while busy', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    mockUpload.mockImplementation((_file, onProgress) => {
      onProgress?.(0.42);
      return new Promise(() => {});
    });
    renderWithProviders(<ImportDialog onClose={onClose} />);

    await chooseFileAndImport(user);

    expect(await screen.findByText('Uploading… 42%')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Close' })).toBeDisabled();
  });

  it('closes from the report', async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    mockUpload.mockResolvedValue('imp-1');
    mockRun.mockResolvedValue(emptyReport());
    renderWithProviders(<ImportDialog onClose={onClose} />);

    await chooseFileAndImport(user);
    const dialog = await screen.findByRole('dialog');
    await waitFor(() => expect(within(dialog).getByText(/0 notes created/)).toBeInTheDocument());
    await user.click(within(dialog).getByRole('button', { name: 'Done' }));

    expect(onClose).toHaveBeenCalled();
  });
});
