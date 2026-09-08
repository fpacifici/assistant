/** Two-panel layout: sidebar (notebooks + notes) and main area (editor). URL params drive visibility. */

import { useParams, Link } from 'react-router';
import { useQuery } from '@tanstack/react-query';
import NotebookList from './NotebookList';
import NoteList from './NoteList';
import NoteEditor from './NoteEditor';
import { useAuth } from '../contexts/AuthContext';
import { fetchInvitesConfig } from '../api/invites';

export default function Layout() {
  const { notebookId, noteId } = useParams();
  const { user, logout } = useAuth();

  const { data: invitesConfig } = useQuery({
    queryKey: ['invites', 'config'],
    queryFn: fetchInvitesConfig,
  });

  return (
    <div className="app-shell">
      <header className="app-header">
        <span className="app-title">Assistant</span>
        <div className="header-user">
          {invitesConfig?.invites_enabled && (
            <Link to="/invites" className="nav-link">Invites</Link>
          )}
          <span className="quota-badge">{user.invite_quota_remaining} invites left</span>
          <span className="user-name">{user.firstname} {user.lastname}</span>
          <button className="btn-logout" onClick={logout}>Logout</button>
        </div>
      </header>
      <div className="layout">
        <div className="sidebar">
          <NotebookList />
          {notebookId && <NoteList />}
        </div>
        <div className="main">
          {noteId ? <NoteEditor /> : (
            <div className="editor-placeholder">
              {notebookId ? 'Select a note to edit' : 'Select a notebook to get started'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
