/** Route table for the data router. Public pages sit at the top level; everything else requires auth. */

import { Navigate } from 'react-router';
import type { RouteObject } from 'react-router';
import Layout from './components/Layout';
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import AcceptInvitePage from './pages/AcceptInvitePage';
import ConfirmEmailPage from './pages/ConfirmEmailPage';
import InvitesPage from './pages/InvitesPage';
import SettingsPage from './pages/SettingsPage';
import SwitchToGooglePage from './pages/SwitchToGooglePage';
import NoteWindow from './pages/NoteWindow';
import {
  ProtectedLayout,
  RootProviders,
  RouteErrorElement,
} from './components/RouteLayouts';

// The three note routes are siblings rendering the same `<Layout />` element
// at the same position, so React reuses the Layout (and NoteEditor) instance
// when navigating between them.
export const routes: RouteObject[] = [
  {
    element: <RootProviders />,
    errorElement: <RouteErrorElement />,
    children: [
      { path: '/login', element: <LoginPage /> },
      { path: '/login/switch-to-google', element: <SwitchToGooglePage /> },
      { path: '/register', element: <RegisterPage /> },
      { path: '/invite/:inviteId', element: <AcceptInvitePage /> },
      { path: '/confirm-email/:token', element: <ConfirmEmailPage /> },
      {
        element: <ProtectedLayout />,
        children: [
          { index: true, element: <Navigate to="/notebooks" replace /> },
          { path: '/notebooks', element: <Layout /> },
          { path: '/notebooks/:notebookId/notes', element: <Layout /> },
          { path: '/notebooks/:notebookId/notes/:noteId', element: <Layout /> },
          { path: '/notebooks/:notebookId/notes/:noteId/window', element: <NoteWindow /> },
          { path: '/invites', element: <InvitesPage /> },
          { path: '/settings', element: <SettingsPage /> },
          { path: '*', element: null },
        ],
      },
    ],
  },
];
