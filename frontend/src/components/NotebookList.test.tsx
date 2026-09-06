import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import NotebookList from './NotebookList';
import { renderWithProviders } from '../test/renderWithProviders';

vi.mock('../api/notebooks', () => ({
  fetchNotebooks: vi.fn(),
  createNotebook: vi.fn(),
  deleteNotebook: vi.fn(),
}));

import { fetchNotebooks, createNotebook, deleteNotebook } from '../api/notebooks';

const mockFetch = vi.mocked(fetchNotebooks);
const mockCreate = vi.mocked(createNotebook);
const mockDelete = vi.mocked(deleteNotebook);

describe('NotebookList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state', () => {
    mockFetch.mockReturnValue(new Promise(() => {}));
    renderWithProviders(<NotebookList />);
    expect(screen.getByText('Loading notebooks...')).toBeInTheDocument();
  });

  it('renders notebook list', async () => {
    mockFetch.mockResolvedValue([
      { id: 'nb-1', name: 'My Notebook', owner_id: 'test-user', permissions: ['view_notebook'] },
      { id: 'nb-2', name: 'Work Notes', owner_id: 'test-user', permissions: ['view_notebook'] },
    ]);
    renderWithProviders(<NotebookList />);

    await waitFor(() => {
      expect(screen.getByText('My Notebook')).toBeInTheDocument();
    });
    expect(screen.getByText('Work Notes')).toBeInTheDocument();
  });

  it('shows empty state when no notebooks', async () => {
    mockFetch.mockResolvedValue([]);
    renderWithProviders(<NotebookList />);

    await waitFor(() => {
      expect(screen.getByText('No notebooks yet')).toBeInTheDocument();
    });
  });

  it('creates a notebook on form submit', async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue([]);
    mockCreate.mockResolvedValue({
      id: 'nb-new',
      name: 'New NB',
      owner_id: 'test-user',
      permissions: ['view_notebook'],
    });

    renderWithProviders(<NotebookList />);
    await waitFor(() => {
      expect(screen.getByPlaceholderText('New notebook name')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('New notebook name');
    await user.type(input, 'New NB');
    await user.click(screen.getByText('Create'));

    await waitFor(() => {
      expect(mockCreate).toHaveBeenCalledWith('New NB');
    });
  });

  it('disables create button when input is empty', async () => {
    mockFetch.mockResolvedValue([]);
    renderWithProviders(<NotebookList />);

    await waitFor(() => {
      expect(screen.getByText('Create')).toBeDisabled();
    });
  });

  it('calls delete when delete button is clicked', async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue([
      { id: 'nb-1', name: 'To Delete', owner_id: 'test-user', permissions: ['delete_notebook'] },
    ]);
    mockDelete.mockResolvedValue(undefined);

    renderWithProviders(<NotebookList />);
    await waitFor(() => {
      expect(screen.getByText('To Delete')).toBeInTheDocument();
    });

    await user.click(screen.getByTitle('Delete notebook'));

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith('nb-1');
    });
  });

  it('highlights active notebook', async () => {
    mockFetch.mockResolvedValue([
      { id: 'nb-1', name: 'Active NB', owner_id: 'test-user', permissions: ['view_notebook'] },
    ]);
    renderWithProviders(<NotebookList />, {
      initialEntries: ['/notebooks/nb-1/notes'],
    });

    await waitFor(() => {
      expect(screen.getByText('Active NB')).toBeInTheDocument();
    });
  });

});

describe('NotebookList permission gating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('hides share and delete buttons when permissions lack them', async () => {
    mockFetch.mockResolvedValue([
      { id: 'nb-1', name: 'Read Only', owner_id: 'other-user', permissions: ['view_notebook'] },
    ]);
    renderWithProviders(<NotebookList />);

    await waitFor(() => {
      expect(screen.getByText('Read Only')).toBeInTheDocument();
    });
    expect(screen.queryByTitle('Share notebook')).not.toBeInTheDocument();
    expect(screen.queryByTitle('Delete notebook')).not.toBeInTheDocument();
  });

  it('shows share button when share_notebook permission is present', async () => {
    mockFetch.mockResolvedValue([
      { id: 'nb-1', name: 'Shared', owner_id: 'other-user', permissions: ['view_notebook', 'share_notebook'] },
    ]);
    renderWithProviders(<NotebookList />);

    await waitFor(() => {
      expect(screen.getByTitle('Share notebook')).toBeInTheDocument();
    });
    expect(screen.queryByTitle('Delete notebook')).not.toBeInTheDocument();
  });
});
