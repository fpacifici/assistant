/** Desktop header: app title, search box, Ask AI (when enabled), Invites, Settings and
 * TUI-layout links, quota, theme picker, user name and Logout. */

import { Link, useLocation } from 'react-router';
import SearchBox from './SearchBox';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../contexts/AuthContext';
import { fetchInvitesConfig } from '../api/invites';
import { ThemeSelect } from './ThemeSwitcher';
import { useAskEnabled } from '../hooks/useAskEnabled';

export default function DesktopHeader() {
  const { user, logout } = useAuth();
  const location = useLocation();
  // On the search page the box shows the current query; elsewhere it's empty.
  const currentQuery =
    location.pathname === '/search' ? (new URLSearchParams(location.search).get('q') ?? '') : '';

  const { data: invitesConfig } = useQuery({
    queryKey: ['invites', 'config'],
    queryFn: fetchInvitesConfig,
  });
  const askEnabled = useAskEnabled();

  return (
    <header className="app-header">
      <span className="app-title">Assistant</span>
      <SearchBox key={location.search} initialQuery={currentQuery} />
      <div className="header-user">
        {askEnabled && (
          <Link to="/ask" className="nav-link">Ask AI</Link>
        )}
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
