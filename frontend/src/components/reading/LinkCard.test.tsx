import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LinkCard from './LinkCard';
import { ApiError } from '../../api/client';
import { linkDomain, linkMarkdown } from '../../lib/readingLinks';
import { readingLink } from '../../test/readingLinks';
import { renderWithProviders } from '../../test/renderWithProviders';
import type { Category, ReadingLink } from '../../types';

vi.mock('../../api/ask', () => ({ fetchAskStatus: vi.fn() }));

vi.mock('../../api/reading', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api/reading')>()),
  updateLink: vi.fn(),
  discardLink: vi.fn(),
  restoreLink: vi.fn(),
  retryLink: vi.fn(),
  deleteLink: vi.fn(),
}));

import { fetchAskStatus } from '../../api/ask';
import { deleteLink, discardLink, restoreLink, retryLink, updateLink } from '../../api/reading';

const CATEGORIES: Category[] = [
  { id: 'c1', name: 'Tech', description: 'Databases', created_at: '2026-10-01T00:00:00Z' },
];

const onPromote = vi.fn();

function render(link: ReadingLink, path = '/reading') {
  return renderWithProviders(
    <ul>
      <LinkCard link={link} categories={CATEGORIES} onPromote={onPromote} />
    </ul>,
    { initialEntries: [path] },
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchAskStatus).mockResolvedValue({ enabled: true });
  vi.mocked(updateLink).mockImplementation(async (_id, changes) => readingLink(changes as Partial<ReadingLink>));
  vi.mocked(discardLink).mockResolvedValue(readingLink({ state: 'discarded' }));
  vi.mocked(restoreLink).mockResolvedValue(readingLink());
  vi.mocked(retryLink).mockResolvedValue(readingLink({ analysis_status: 'pending' }));
  vi.mocked(deleteLink).mockResolvedValue(undefined);
});

// --- Content ---

describe('content', () => {
  it('shows title, domain, type, date and summary', () => {
    render(readingLink());
    const title = screen.getByRole('link', { name: 'On B-trees' });
    expect(title).toHaveAttribute('href', 'https://www.example.com/btrees');
    expect(title).toHaveAttribute('target', '_blank');
    expect(screen.getByText('example.com')).toBeInTheDocument();
    expect(screen.getByText('Web page')).toBeInTheDocument();
    expect(screen.getByText(/^Added /)).toBeInTheDocument();
    expect(screen.getByText('B-trees keep data sorted.')).toBeInTheDocument();
  });

  it('shows the URL while nothing names the link, and says it is analyzed', async () => {
    render(readingLink({ title: null, summary: null, link_type: null, analysis_status: 'pending' }));
    expect(
      screen.getByRole('link', { name: 'https://www.example.com/btrees' }),
    ).toBeInTheDocument();
    expect(await screen.findByText('Analyzing…')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry analysis' })).not.toBeInTheDocument();
  });

  it('says a pending link waits when AI is off', async () => {
    vi.mocked(fetchAskStatus).mockResolvedValue({ enabled: false });
    render(readingLink({ summary: null, analysis_status: 'pending' }));
    await waitFor(() => expect(fetchAskStatus).toHaveBeenCalled());
    expect(screen.getByText('Waiting for analysis')).toBeInTheDocument();
  });

  it('is marked and scrolled to when the URL points at it', () => {
    const scroll = vi.fn();
    Element.prototype.scrollIntoView = scroll;
    render(readingLink(), '/reading#link-l1');
    expect(screen.getByRole('listitem')).toHaveClass('targeted');
    expect(scroll).toHaveBeenCalled();
  });

  it('explains a failure', () => {
    render(
      readingLink({
        summary: null,
        analysis_status: 'failed',
        last_error: 'The server answered HTTP 403',
      }),
    );
    expect(screen.getByText('Analysis failed')).toBeInTheDocument();
    expect(screen.getByText(/HTTP 403/)).toBeInTheDocument();
  });

  it('never makes a link of an unsafe URL', () => {
    render(readingLink({ url: 'javascript:alert(1)', title: 'Bad' }));
    expect(screen.queryByRole('link', { name: 'Bad' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open Bad' })).not.toBeInTheDocument();
  });
});

// --- Editing ---

describe('editing', () => {
  it('files the link under a category', async () => {
    const user = userEvent.setup();
    render(readingLink());
    await user.selectOptions(screen.getByLabelText('Category of On B-trees'), 'Tech');
    await waitFor(() => expect(updateLink).toHaveBeenCalledWith('l1', { category_id: 'c1' }));
  });

  it('moves it back to Unfiled', async () => {
    const user = userEvent.setup();
    render(readingLink({ category_id: 'c1' }));
    await user.selectOptions(screen.getByLabelText('Category of On B-trees'), 'Unfiled');
    await waitFor(() => expect(updateLink).toHaveBeenCalledWith('l1', { category_id: null }));
  });

  it('edits the title', async () => {
    const user = userEvent.setup();
    render(readingLink());
    await user.click(screen.getByRole('button', { name: 'Edit title of On B-trees' }));
    const input = screen.getByLabelText('Title');
    await user.clear(input);
    await user.type(input, 'Trees{Enter}');
    await waitFor(() => expect(updateLink).toHaveBeenCalledWith('l1', { title: 'Trees' }));
  });

  it('saves notes when leaving the field', async () => {
    const user = userEvent.setup();
    render(readingLink());
    await user.type(screen.getByLabelText('Notes on On B-trees'), 'Section 3');
    expect(updateLink).not.toHaveBeenCalled();
    await user.tab();
    await waitFor(() =>
      expect(updateLink).toHaveBeenCalledWith('l1', { user_notes: 'Section 3' }),
    );
  });

  it('shows why a change failed', async () => {
    vi.mocked(updateLink).mockRejectedValue(new ApiError(404, 'Not found'));
    const user = userEvent.setup();
    render(readingLink());
    await user.selectOptions(screen.getByLabelText('Category of On B-trees'), 'Tech');
    expect(await screen.findByText('Not found')).toBeInTheDocument();
  });
});

// --- Actions ---

describe('actions', () => {
  it('to read: open, promote, discard and retry', async () => {
    const user = userEvent.setup();
    render(readingLink());
    expect(screen.getByRole('link', { name: 'Open On B-trees' })).toHaveAttribute(
      'target',
      '_blank',
    );
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Promote' }));
    expect(onPromote).toHaveBeenCalledWith(expect.objectContaining({ id: 'l1' }));
    await user.click(screen.getByRole('button', { name: 'Discard' }));
    await waitFor(() => expect(discardLink).toHaveBeenCalledWith('l1'));
    await user.click(screen.getByRole('button', { name: 'Retry analysis' }));
    await waitFor(() => expect(retryLink).toHaveBeenCalledWith('l1'));
  });

  it('archive: restore, and delete after confirming', async () => {
    const user = userEvent.setup();
    render(readingLink({ state: 'discarded' }));
    expect(screen.queryByRole('button', { name: 'Promote' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Restore' }));
    await waitFor(() => expect(restoreLink).toHaveBeenCalledWith('l1'));
    await user.click(screen.getByRole('button', { name: 'Delete' }));
    await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(deleteLink).toHaveBeenCalledWith('l1'));
  });

  it('promoted: links to its note and can only be deleted', () => {
    render(readingLink({ state: 'promoted', note_id: 'n1', note_notebook_id: 'nb1' }));
    expect(screen.getByRole('link', { name: 'Open note' })).toHaveAttribute(
      'href',
      '/notebooks/nb1/notes/n1',
    );
    expect(screen.queryByRole('button', { name: 'Restore' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Discard' })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });

  it('promoted to a note since deleted', () => {
    render(readingLink({ state: 'promoted' }));
    expect(screen.getByText('Note deleted')).toBeInTheDocument();
  });
});

// --- Helpers ---

describe('helpers', () => {
  it('formats markdown and escapes brackets in the title', () => {
    expect(linkMarkdown(readingLink({ title: 'A [draft]' }))).toBe(
      '[A \\[draft\\]](https://www.example.com/btrees)\n\nB-trees keep data sorted.',
    );
    expect(linkMarkdown(readingLink({ summary: null }))).toBe(
      '[On B-trees](https://www.example.com/btrees)',
    );
  });

  it('shows the domain without www', () => {
    expect(linkDomain('https://www.example.com/x')).toBe('example.com');
    expect(linkDomain('not a url')).toBe('not a url');
  });
});
