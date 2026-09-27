/** Pathless layout-route elements used by `routes.tsx`. */

import { useEffect } from 'react';
import { Outlet, useRouteError } from 'react-router';
import * as Sentry from '@sentry/react';
import { AuthProvider } from '../contexts/AuthContext';
import { LayoutModeProvider } from '../layout/LayoutModeContext';

function ErrorFallback() {
  return (
    <div className="loading" role="alert">
      Something went wrong.{' '}
      <button type="button" onClick={() => window.location.reload()}>
        Reload
      </button>
    </div>
  );
}

/** Root route element: app-wide providers that need router context. */
export function RootProviders() {
  return (
    <LayoutModeProvider>
      <Sentry.ErrorBoundary fallback={<ErrorFallback />}>
        <Outlet />
      </Sentry.ErrorBoundary>
    </LayoutModeProvider>
  );
}

/**
 * Root route `errorElement`: the data router catches loader and render errors
 * itself, so they never reach a React error boundary — report them here.
 */
export function RouteErrorElement() {
  const error = useRouteError();
  useEffect(() => {
    Sentry.captureException(error);
  }, [error]);
  return <ErrorFallback />;
}

/** Wraps every authenticated route; redirects to /login when there is no session. */
export function ProtectedLayout() {
  return (
    <AuthProvider>
      <Outlet />
    </AuthProvider>
  );
}
