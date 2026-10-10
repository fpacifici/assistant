/** Desktop header: app title, Invites, Settings and TUI-layout links, quota, theme picker, user
 * name and Logout. */

import { Link } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { fetchInvitesConfig } from '../api/invites';
import { ThemeSelect } from './ThemeSwitcher';

export default function DesktopHeader() {
  const { user, logout } = useAuth();

  const { data: invitesConfig } = useQuery({
    queryKey: ['invites', 'config'],
    queryFn: fetchInvitesConfig,
  });

  return (
    <header className="app-header">
      <span className="app-title">Assistant</span>
      <div className="header-user">
        {invitesConfig?.invites_enabled && (
          <Link to="/invites" className="nav-link">Invites</Link>
        )}
        <Link to="/settings" className="nav-link">Settings</Link>
        <Link
          to="?layout=tui"
          className="nav-link"
          title="Terminal-style layout with keyboard shortcuts"
        >
          TUI
        </Link>
        <span className="quota-badge">{user.invite_quota_remaining} invites left</span>
        <ThemeSelect />
        <span className="user-name">{user.firstname} {user.lastname}</span>
        <button className="btn-logout" onClick={logout}>Logout</button>
      </div>
    </header>
  );
}
