/** Text shown for reading links. */

import type { ReadingLink } from '../types';

/** The title, or the URL while nothing names the link. */
export function linkTitle(link: ReadingLink): string {
  return link.title ?? link.url;
}

/** The host without `www.`, or the URL if it doesn't parse. */
export function linkDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

/** `[title](url)` and the summary, for the clipboard. */
export function linkMarkdown(link: ReadingLink): string {
  const title = linkTitle(link).replace(/[[\]]/g, '\\$&');
  const markdown = `[${title}](${link.url})`;
  return link.summary ? `${markdown}\n\n${link.summary}` : markdown;
}
