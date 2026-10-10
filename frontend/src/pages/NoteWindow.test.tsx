import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import { Route, Routes } from 'react-router';
import NoteWindow from './NoteWindow';
import { renderWithProviders } from '../test/renderWithProviders';
import type { LayoutMode } from '../layout/layoutMode';

vi.mock('../api/notes', () => ({
  fetchNote: vi.fn().mockResolvedValue({
    id: 'note-1', notebook_id: 'nb-1', owner_id: 'u1', title: 'Hilbert curves',
    creation_timestamp: '', update_timestamp: '', permissions: [], tags: [], preview: '',
  }),
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    user: { uid: 'u1', email: 'a@b.com', firstname: 'A', lastname: 'B', invite_quota_remaining: 1 },
    logout: vi.fn(),
  }),
}));

vi.mock('../api/invites', () => ({
  fetchInvitesConfig: vi.fn().mockResolvedValue({
    registration_enabled: true,
    invites_enabled: false,
  }),
}));

vi.mock('../components/NoteEditor', () => ({
  default: ({ standalone }: { standalone?: boolean }) => (
    <div data-testid="note-editor" data-standalone={String(!!standalone)} />
  ),
}));

function renderWindow(layout: LayoutMode = 'desktop') {
  return renderWithProviders(
    <Routes>
      <Route path="/notebooks/:notebookId/notes/:noteId/window" element={<NoteWindow />} />
    </Routes>,
    { initialEntries: ['/notebooks/nb-1/notes/note-1/window'], layout },
  );
}

beforeEach(() => {
  document.title = 'Assistant';
});

// --- Desktop ---

it('shows only the standalone editor under the note title', async () => {
  const { container } = renderWindow();

  expect(await screen.findByRole('heading', { name: 'Hilbert curves' })).toBeInTheDocument();
  expect(screen.getByTestId('note-editor')).toHaveAttribute('data-standalone', 'true');
  expect(container.querySelector('.sidebar')).not.toBeInTheDocument();
  expect(container.querySelector('.notes-column')).not.toBeInTheDocument();
});

it('titles the browser window with the note title and restores it on unmount', async () => {
  const { unmount } = renderWindow();
  await waitFor(() => expect(document.title).toBe('Hilbert curves'));

  unmount();
  expect(document.title).toBe('Assistant');
});

// --- Mobile ---

describe('on mobile', () => {
  it('uses the mobile top bar without a back link', async () => {
    renderWindow('mobile');
    expect(await screen.findByRole('heading', { name: 'Hilbert curves' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Back' })).not.toBeInTheDocument();
  });
});
