/** Post URLs come from feeds, so `javascript:` and the like must never become a link. */
export function isSafeLink(url: string): boolean {
  try {
    const { protocol } = new URL(url);
    return protocol === 'http:' || protocol === 'https:';
  } catch {
    return false;
  }
}
