import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import NotebookList from './NotebookList';
import { renderWithProviders } from '../test/renderWithProviders';
import { TopBarMenuProvider, useRegisteredMenuItems } from './TopBarMenuContext';

vi.mock('../api/notebooks', () => ({
  fetchNotebooks: vi.fn(),
  createNotebook: vi.fn(),
  deleteNotebook: vi.fn(),
}));

import { fetchNotebooks, createNotebook, deleteNotebook } from '../api/notebooks';
import { PAGE_SIZE } from '../api/pagination';
import type { Notebook } from '../types';
import { mockIntersectionObserver, scrollIntoView } from '../test/intersectionObserver';

const mockFetch = vi.mocked(fetchNotebooks);
const mockCreate = vi.mocked(createNotebook);
const mockDelete = vi.mocked(deleteNotebook);

function makeNotebook(i: number, name = `Notebook ${i}`): Notebook {
  return { id: `nb-${i}`, name, owner_id: 'test-user', permissions: ['view_notebook'] };
}

describe('NotebookList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIntersectionObserver();
  });

  it('loads the next page when the end of the list scrolls into view', async () => {
    const firstPage = Array.from({ length: PAGE_SIZE }, (_, i) => makeNotebook(i));
    mockFetch
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce([makeNotebook(PAGE_SIZE, 'Zebra')]);
    const { container } = renderWithProviders(<NotebookList />);
    await screen.findByText('Notebook 0');
    expect(mockFetch).toHaveBeenCalledWith(0);

    scrollIntoView(container.querySelector('.list-sentinel')!);

    expect(await screen.findByText('Zebra')).toBeInTheDocument();
    expect(mockFetch).toHaveBeenLastCalledWith(PAGE_SIZE);
    expect(container.querySelector('.list-sentinel')).not.toBeInTheDocument();
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

  it('asks for confirmation and deletes on confirm', async () => {
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

    const dialog = screen.getByRole('alertdialog');
    expect(dialog).toHaveTextContent('Delete notebook "To Delete"? This cannot be undone.');
    expect(mockDelete).not.toHaveBeenCalled();

    await user.click(within(dialog).getByRole('button', { name: 'Delete' }));

    await waitFor(() => {
      expect(mockDelete).toHaveBeenCalledWith('nb-1');
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('does not delete when the confirmation is cancelled', async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue([
      { id: 'nb-1', name: 'Keep Me', owner_id: 'test-user', permissions: ['delete_notebook'] },
    ]);

    renderWithProviders(<NotebookList />);
    await screen.findByText('Keep Me');

    await user.click(screen.getByTitle('Delete notebook'));
    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(mockDelete).not.toHaveBeenCalled();
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

  it('opens the import dialog from the Import button', async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue([]);
    renderWithProviders(<NotebookList />);

    await user.click(await screen.findByRole('button', { name: 'Import' }));

    expect(screen.getByRole('dialog', { name: 'Import from Evernote' })).toBeInTheDocument();
  });

  it('registers an "Import from Evernote" entry for the mobile menu', async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue([]);
    function MenuItems() {
      return (
        <>
          {useRegisteredMenuItems().map((item) => (
            <button key={item.id} onClick={item.onSelect}>
              {item.label}
            </button>
          ))}
        </>
      );
    }
    renderWithProviders(
      <TopBarMenuProvider>
        <MenuItems />
        <NotebookList />
      </TopBarMenuProvider>,
      { layout: 'mobile' },
    );

    await user.click(await screen.findByRole('button', { name: 'Import from Evernote' }));

    expect(screen.getByRole('dialog', { name: 'Import from Evernote' })).toBeInTheDocument();
  });
});
