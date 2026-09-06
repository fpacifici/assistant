import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ShareDialog from './ShareDialog';
import { renderWithProviders } from '../test/renderWithProviders';
import { ApiError } from '../api/client';

vi.mock('../api/notebooks', () => ({
  fetchNotebookEntitlements: vi.fn(),
  shareNotebook: vi.fn(),
  revokeNotebookEntitlement: vi.fn(),
}));
vi.mock('../api/notes', () => ({
  fetchNoteEntitlements: vi.fn(),
  shareNote: vi.fn(),
  revokeNoteEntitlement: vi.fn(),
}));

import {
  fetchNotebookEntitlements,
  shareNotebook,
  revokeNotebookEntitlement,
} from '../api/notebooks';

const mockFetch = vi.mocked(fetchNotebookEntitlements);
const mockShare = vi.mocked(shareNotebook);
const mockRevoke = vi.mocked(revokeNotebookEntitlement);

const ROLE_OPTIONS = ['notebook_viewer', 'notebook_editor', 'notebook_owner'];

describe('ShareDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders current entitlements', async () => {
    mockFetch.mockResolvedValue([
      {
        id: 'ent-1',
        principal_id: 'u-1',
        principal_email: 'alice@test.com',
        role: 'notebook_viewer',
        created_at: '',
      },
    ]);
    renderWithProviders(
      <ShareDialog
        subjectType="notebook"
        notebookId="nb-1"
        roleOptions={ROLE_OPTIONS}
        onClose={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('alice@test.com')).toBeInTheDocument();
    });
    expect(screen.getByText('alice@test.com').closest('li')).toHaveTextContent(
      'notebook_viewer',
    );
  });

  it('submitting the form calls the share mutation with entered email/role', async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue([]);
    mockShare.mockResolvedValue({
      id: 'ent-2',
      principal_id: 'u-2',
      principal_email: 'bob@test.com',
      role: 'notebook_editor',
      created_at: '',
    });

    renderWithProviders(
      <ShareDialog
        subjectType="notebook"
        notebookId="nb-1"
        roleOptions={ROLE_OPTIONS}
        onClose={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Email address')).toBeInTheDocument();
    });
    await user.type(screen.getByPlaceholderText('Email address'), 'bob@test.com');
    await user.selectOptions(screen.getByRole('combobox'), 'notebook_editor');
    await user.click(screen.getByText('Share'));

    await waitFor(() => {
      expect(mockShare).toHaveBeenCalledWith('nb-1', 'bob@test.com', 'notebook_editor');
    });
  });

  it('renders an inline message for a 404 response', async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue([]);
    mockShare.mockRejectedValue(new ApiError(404, 'User not found'));

    renderWithProviders(
      <ShareDialog
        subjectType="notebook"
        notebookId="nb-1"
        roleOptions={ROLE_OPTIONS}
        onClose={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Email address')).toBeInTheDocument();
    });
    await user.type(screen.getByPlaceholderText('Email address'), 'nobody@test.com');
    await user.click(screen.getByText('Share'));

    await waitFor(() => {
      expect(screen.getByText('User not found')).toBeInTheDocument();
    });
  });

  it('renders an inline message for a 403 response', async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue([]);
    mockShare.mockRejectedValue(new ApiError(403, 'Missing share_notebook permission'));

    renderWithProviders(
      <ShareDialog
        subjectType="notebook"
        notebookId="nb-1"
        roleOptions={ROLE_OPTIONS}
        onClose={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Email address')).toBeInTheDocument();
    });
    await user.type(screen.getByPlaceholderText('Email address'), 'someone@test.com');
    await user.click(screen.getByText('Share'));

    await waitFor(() => {
      expect(screen.getByText('Missing share_notebook permission')).toBeInTheDocument();
    });
  });

  it('clicking Revoke calls the revoke mutation', async () => {
    const user = userEvent.setup();
    mockFetch.mockResolvedValue([
      {
        id: 'ent-1',
        principal_id: 'u-1',
        principal_email: 'alice@test.com',
        role: 'notebook_viewer',
        created_at: '',
      },
    ]);
    mockRevoke.mockResolvedValue(undefined);

    renderWithProviders(
      <ShareDialog
        subjectType="notebook"
        notebookId="nb-1"
        roleOptions={ROLE_OPTIONS}
        onClose={() => {}}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText('alice@test.com')).toBeInTheDocument();
    });
    await user.click(screen.getByTitle('Revoke'));

    await waitFor(() => {
      expect(mockRevoke).toHaveBeenCalledWith('nb-1', 'ent-1');
    });
  });
});
