import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useMemo } from 'react';
import OverflowMenu from './OverflowMenu';
import { TopBarMenuProvider, useTopBarMenuItems } from './TopBarMenuContext';
import { renderWithProviders } from '../test/renderWithProviders';

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

const onExtra = vi.fn();

function Registrar() {
  const items = useMemo(() => [{ id: 'extra', label: 'Extra action', onSelect: onExtra }], []);
  useTopBarMenuItems(items);
  return null;
}

function renderMenu({ withRegistrar = false } = {}) {
  return renderWithProviders(
    <TopBarMenuProvider>
      <p>outside</p>
      <OverflowMenu />
      {withRegistrar && <Registrar />}
    </TopBarMenuProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

// --- Open / close ---

describe('OverflowMenu', () => {
  it('toggles open and closed with the Menu button', async () => {
    const user = userEvent.setup();
    renderMenu();
    const button = screen.getByRole('button', { name: 'Menu' });
    expect(button).toHaveAttribute('aria-expanded', 'false');

    await user.click(button);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    expect(button).toHaveAttribute('aria-expanded', 'true');

    await user.click(button);
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('closes on Escape', async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('closes on an outside click', async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    await user.click(screen.getByText('outside'));
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  it('stays open when clicking non-item content inside it', async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    await user.click(screen.getByText('A B'));
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });

  // --- Registered items ---

  it('shows registered items and closes after activating one', async () => {
    const user = userEvent.setup();
    renderMenu({ withRegistrar: true });
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    await user.click(screen.getByRole('menuitem', { name: 'Extra action' }));
    expect(onExtra).toHaveBeenCalled();
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
  });

  // --- Theme ---

  it('switches the theme and stays open', async () => {
    const user = userEvent.setup();
    renderMenu();
    await user.click(screen.getByRole('button', { name: 'Menu' }));
    expect(screen.getByRole('menuitemradio', { name: 'System' })).toHaveAttribute('aria-checked', 'true');

    await user.click(screen.getByRole('menuitemradio', { name: 'Dark' }));
    expect(screen.getByRole('menuitemradio', { name: 'Dark' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByRole('menuitemradio', { name: 'System' })).toHaveAttribute('aria-checked', 'false');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(screen.getByRole('menu')).toBeInTheDocument();
  });
});
