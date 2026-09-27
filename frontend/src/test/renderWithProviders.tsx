import { render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { createMemoryRouter, RouterProvider } from 'react-router';
import type { RouteObject } from 'react-router';
import type { ReactElement } from 'react';

/**
 * Render under a data router (memory history) and a QueryClient.
 *
 * `ui` becomes the element of a catch-all route, so callers may pass either a
 * plain component or their own `<Routes>` tree. Pass `routes` instead of `ui`
 * (use `null`) to supply a full route table. The returned `router` can be
 * used to navigate programmatically.
 */
export function renderWithProviders(
  ui: ReactElement | null,
  {
    initialEntries = ['/'],
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    }),
    routes,
  }: {
    initialEntries?: string[];
    queryClient?: QueryClient;
    routes?: RouteObject[];
  } = {},
) {
  const router = createMemoryRouter(routes ?? [{ path: '*', element: ui }], {
    initialEntries,
  });
  const result = render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { ...result, router };
}
