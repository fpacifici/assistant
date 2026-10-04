import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, Outlet, RouterProvider } from 'react-router';
import type { RouteObject } from 'react-router';
import type { ReactElement } from 'react';
import { LayoutModeProvider } from '../layout/LayoutModeContext';
import { ThemeProvider } from '../theme/ThemeContext';
import type { LayoutMode } from '../layout/layoutMode';

/**
 * Render under a data router (memory history), a QueryClient, the theme
 * provider and a layout mode.
 *
 * `ui` becomes the element of a catch-all route, so callers may pass either a
 * plain component or their own `<Routes>` tree. Pass `routes` instead of `ui`
 * (use `null`) to supply a full route table. The returned `router` can be
 * used to navigate programmatically.
 *
 * `layout` forces the layout mode (default `'desktop'`); `'auto'` uses real
 * detection from `window.matchMedia` (see `test/matchMedia.ts`) and the
 * `?layout=` override.
 */
export function renderWithProviders(
  ui: ReactElement | null,
  {
    initialEntries = ['/'],
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    }),
    routes,
    layout = 'desktop',
  }: {
    initialEntries?: string[];
    queryClient?: QueryClient;
    routes?: RouteObject[];
    layout?: LayoutMode | 'auto';
  } = {},
) {
  const forcedMode = layout === 'auto' ? undefined : layout;
  const router = createMemoryRouter(
    [
      {
        element: (
          <ThemeProvider>
            <LayoutModeProvider forcedMode={forcedMode}>
              <Outlet />
            </LayoutModeProvider>
          </ThemeProvider>
        ),
        children: routes ?? [{ path: '*', element: ui }],
      },
    ],
    { initialEntries },
  );
  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...result, router };
}
