import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { act, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { useParams } from 'react-router';
import { routes } from './routes';
import { renderWithProviders } from './test/renderWithProviders';

vi.mock('./api/auth', () => ({
  getMe: vi.fn(),
  logout: vi.fn(),
}));

// Stateful stand-in for Layout: local state survives only if the instance is reused.
vi.mock('./components/Layout', () => ({
  default: function FakeLayout() {
    const { noteId } = useParams();
    const [text, setText] = useState('');
    return (
      <div data-testid="layout">
        <span data-testid="note-id">{noteId ?? 'none'}</span>
        <input aria-label="scratch" value={text} onChange={(e) => setText(e.target.value)} />
      </div>
    );
  },
}));

import { getMe } from './api/auth';
const mockGetMe = vi.mocked(getMe);

const USER = {
  uid: 'u1',
  email: 'a@b.com',
  firstname: 'A',
  lastname: 'B',
  invite_quota_remaining: 3,
};

const originalLocation = window.location;

beforeEach(() => {
  vi.clearAllMocks();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...originalLocation, href: 'http://localhost/' },
  });
});

afterEach(() => {
  Object.defineProperty(window, 'location', { configurable: true, value: originalLocation });
});

// --- Redirects ---

it('redirects / to /notebooks', async () => {
  mockGetMe.mockResolvedValue(USER);
  const { router } = renderWithProviders(null, { routes, initialEntries: ['/'] });

  await screen.findByTestId('layout');
  expect(router.state.location.pathname).toBe('/notebooks');
});

it('sends unauthenticated users on protected routes to /login', async () => {
  mockGetMe.mockRejectedValue(new Error('401'));
  renderWithProviders(null, { routes, initialEntries: ['/notebooks'] });

  await waitFor(() => expect(window.location.href).toBe('/login'));
  expect(screen.queryByTestId('layout')).not.toBeInTheDocument();
});

// --- Layout instance sharing ---

describe('note routes', () => {
  it('reuse the same Layout instance across note, notebook and list URLs', async () => {
    mockGetMe.mockResolvedValue(USER);
    const user = userEvent.setup();
    const { router } = renderWithProviders(null, {
      routes,
      initialEntries: ['/notebooks/nb-1/notes/note-1'],
    });

    await user.type(await screen.findByLabelText('scratch'), 'kept');

    await act(() => router.navigate('/notebooks/nb-1/notes/note-2'));
    expect(screen.getByTestId('note-id')).toHaveTextContent('note-2');
    expect(screen.getByLabelText('scratch')).toHaveValue('kept');

    await act(() => router.navigate('/notebooks/nb-1/notes'));
    expect(screen.getByTestId('note-id')).toHaveTextContent('none');
    expect(screen.getByLabelText('scratch')).toHaveValue('kept');

    await act(() => router.navigate('/notebooks'));
    expect(screen.getByLabelText('scratch')).toHaveValue('kept');
  });
});
