/** Desktop header: app title, the top-level sections (Notes, and Blogs and Reading
 * when AI is enabled), search box, Ask AI (when AI is enabled), Invites, Settings and TUI-layout
 * links, quota, theme picker, user name and Logout. */

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

  const section = (to: string, prefix: string, label: string) => {
    const active = location.pathname.startsWith(prefix);
    return (
      <Link
        to={to}
        className={`app-section${active ? ' active' : ''}`}
        aria-current={active ? 'page' : undefined}
      >
        {label}
      </Link>
    );
  };

  return (
    <header className="app-header">
      <div className="app-header-start">
        <span className="app-title">Assistant</span>
        <nav className="app-sections" aria-label="Sections">
          {section('/notebooks', '/notebooks', 'Notes')}
          {askEnabled && section('/blogs/triage', '/blogs', 'Blogs')}
          {askEnabled && section('/reading', '/reading', 'Reading')}
        </nav>
      </div>
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
