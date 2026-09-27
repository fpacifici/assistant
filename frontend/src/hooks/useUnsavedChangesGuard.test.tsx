import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { Link } from 'react-router';
import { useUnsavedChangesGuard } from './useUnsavedChangesGuard';
import { renderWithProviders } from '../test/renderWithProviders';

function Editor() {
  const [dirty, setDirty] = useState(false);
  const dialog = useUnsavedChangesGuard(dirty);
  return (
    <div>
      <h1>Editor</h1>
      <button onClick={() => setDirty(true)}>Edit</button>
      <button onClick={() => setDirty(false)}>Save</button>
      <Link to="/elsewhere">Leave</Link>
      {dialog}
    </div>
  );
}

const ROUTES = [
  { path: '/start', element: <h1>Start</h1> },
  { path: '/editor', element: <Editor /> },
  { path: '/elsewhere', element: <h1>Elsewhere</h1> },
];

function renderGuarded() {
  // History: /start -> /editor, so navigate(-1) goes back to /start.
  return renderWithProviders(null, {
    routes: ROUTES,
    initialEntries: ['/start', '/editor'],
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

// --- Clean state ---

describe('useUnsavedChangesGuard when clean', () => {
  it('lets navigation through without a dialog', async () => {
    const user = userEvent.setup();
    renderGuarded();
    await user.click(screen.getByRole('link', { name: 'Leave' }));
    expect(screen.getByRole('heading', { name: 'Elsewhere' })).toBeInTheDocument();
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('lets navigation through after saving', async () => {
    const user = userEvent.setup();
    renderGuarded();
    await user.click(screen.getByRole('button', { name: 'Edit' }));
    await user.click(screen.getByRole('button', { name: 'Save' }));
    await user.click(screen.getByRole('link', { name: 'Leave' }));
    expect(screen.getByRole('heading', { name: 'Elsewhere' })).toBeInTheDocument();
  });
});

// --- Dirty state ---

describe('useUnsavedChangesGuard when dirty', () => {
  it('blocks a link click; Keep editing stays on the page', async () => {
    const user = userEvent.setup();
    const { router } = renderGuarded();
    await user.click(screen.getByRole('button', { name: 'Edit' }));
    await user.click(screen.getByRole('link', { name: 'Leave' }));

    expect(screen.getByRole('alertdialog', { name: 'Discard unsaved changes?' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Keep editing' }));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Editor' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/editor');
  });

  it('blocks a link click; Discard navigates', async () => {
    const user = userEvent.setup();
    const { router } = renderGuarded();
    await user.click(screen.getByRole('button', { name: 'Edit' }));
    await user.click(screen.getByRole('link', { name: 'Leave' }));
    await user.click(screen.getByRole('button', { name: 'Discard' }));

    expect(screen.getByRole('heading', { name: 'Elsewhere' })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/elsewhere');
  });

  it('blocks history back', async () => {
    const user = userEvent.setup();
    const { router } = renderGuarded();
    await user.click(screen.getByRole('button', { name: 'Edit' }));

    await act(() => router.navigate(-1));

    expect(screen.getByRole('alertdialog')).toBeInTheDocument();
    expect(router.state.location.pathname).toBe('/editor');

    await user.click(screen.getByRole('button', { name: 'Discard' }));
    expect(router.state.location.pathname).toBe('/start');
  });

  it('does not block query-string-only changes', async () => {
    const user = userEvent.setup();
    const { router } = renderGuarded();
    await user.click(screen.getByRole('button', { name: 'Edit' }));

    await act(() => router.navigate('/editor?layout=mobile'));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(router.state.location.search).toBe('?layout=mobile');
  });
});

// --- beforeunload ---

describe('useUnsavedChangesGuard beforeunload', () => {
  it('registers the handler only while dirty', async () => {
    const add = vi.spyOn(window, 'addEventListener');
    const remove = vi.spyOn(window, 'removeEventListener');
    const user = userEvent.setup();
    renderGuarded();

    const registered = () => add.mock.calls.filter(([type]) => type === 'beforeunload');
    expect(registered()).toHaveLength(0);

    await user.click(screen.getByRole('button', { name: 'Edit' }));
    expect(registered()).toHaveLength(1);

    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);

    await user.click(screen.getByRole('button', { name: 'Save' }));
    const handler = registered()[0][1];
    expect(remove).toHaveBeenCalledWith('beforeunload', handler);

    const after = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(after);
    expect(after.defaultPrevented).toBe(false);
  });
});
