/** Page size for list endpoints (the API caps `limit` at 100). */
export const PAGE_SIZE = 50;

/**
 * `getNextPageParam` for offset-paginated infinite queries: a short page
 * means the list is exhausted.
 */
export function nextPageOffset<T>(lastPage: T[], allPages: T[][]): number | undefined {
  return lastPage.length < PAGE_SIZE ? undefined : allPages.length * PAGE_SIZE;
}
