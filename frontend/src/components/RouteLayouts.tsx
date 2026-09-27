/** Pathless layout-route elements used by `routes.tsx`. */

import { Outlet } from 'react-router';
import { AuthProvider } from '../contexts/AuthContext';
import { LayoutModeProvider } from '../layout/LayoutModeContext';

/** Root route element: app-wide providers that need router context. */
export function RootProviders() {
  return (
    <LayoutModeProvider>
      <Outlet />
    </LayoutModeProvider>
  );
}

/** Wraps every authenticated route; redirects to /login when there is no session. */
export function ProtectedLayout() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  );
}
