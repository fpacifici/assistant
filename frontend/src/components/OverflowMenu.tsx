/** Mobile `⋯` menu: account details, Invites, Settings, theme, Logout, plus
 * view-specific entries. */

import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { fetchInvitesConfig } from '../api/invites';
import { useRegisteredMenuItems } from './TopBarMenuContext';
import { ThemeMenuItems } from './ThemeSwitcher';

export default function OverflowMenu({ children }: { children?: React.ReactNode }) {
  const { user, logout } = useAuth();
  const extraItems = useRegisteredMenuItems();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const { data: invitesConfig } = useQuery({
    queryKey: ['invites', 'config'],
    queryFn: fetchInvitesConfig,
  });

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent | TouchEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('touchstart', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('touchstart', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open]);

  // Any activated entry closes the menu.
  const closeOnItem = (e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest('[role="menuitem"]')) setOpen(false);
  };

  return (
    <div className="overflow-menu" ref={rootRef}>
      <button
        className="topbar-btn"
        aria-label="Menu"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((prev) => !prev)}
      >
        &#8943;
      </button>
      {open && (
        <div className="overflow-menu-popover" role="menu" onClick={closeOnItem}>
          <div className="overflow-menu-user">
            <span className="user-name">{user.firstname} {user.lastname}</span>
            <span className="quota-badge">{user.invite_quota_remaining} invites left</span>
          </div>
          {extraItems.map((item) => (
            <button key={item.id} role="menuitem" onClick={item.onSelect}>
              {item.label}
            </button>
          ))}
          {children}
          {invitesConfig?.invites_enabled && (
            <Link role="menuitem" to="/invites">Invites</Link>
          )}
          <Link role="menuitem" to="/settings">Settings</Link>
          <ThemeMenuItems />
          <button role="menuitem" onClick={logout}>Logout</button>
        </div>
      )}
    </div>
  );
}
