/**
 * Sentry setup: errors, tracing (continued into the backend) and session replay.
 *
 * Everything is off unless `VITE_SENTRY_DSN` is set at build time. Traffic that
 * only matches the catch-all route and has no logged-in user (scanners, typos)
 * is neither traced nor replayed; errors are always sent.
 * See docs/architecture/observability.md.
 */

import * as Sentry from '@sentry/react';
import type { Event } from '@sentry/react';
import {
  createRoutesFromChildren,
  matchRoutes,
  useLocation,
  useNavigationType,
} from 'react-router';
import type { RouteObject } from 'react-router';
import type { User } from '../types';

const DEFAULT_TRACES_SAMPLE_RATE = 1.0;
const DEFAULT_REPLAYS_SESSION_SAMPLE_RATE = 0.1;
const DEFAULT_REPLAYS_ON_ERROR_SAMPLE_RATE = 1.0;

let enabled = false;
let replayEnabled = false;

/** Parses a `[0, 1]` sample rate, falling back instead of breaking the app. */
export function parseSampleRate(raw: string | undefined, fallback: number): number {
  if (raw === undefined || raw.trim() === '') return fallback;
  const rate = Number(raw);
  if (!Number.isFinite(rate) || rate < 0 || rate > 1) return fallback;
  return rate;
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Where to attach `sentry-trace`/`baggage` headers. Same-origin requests (the
 * nginx-fronted deployment) are always propagated by the SDK; a cross-origin
 * API base URL (local dev, `:5173` → `:8000`) is added explicitly.
 */
export function buildTracePropagationTargets(
  apiBaseUrl: string | undefined,
): (string | RegExp)[] {
  if (!apiBaseUrl) return [];
  let origin: string;
  try {
    origin = new URL(apiBaseUrl).origin;
  } catch {
    return []; // relative base URL: same origin
  }
  return [new RegExp(`^${escapeRegExp(origin)}(/|$)`)];
}

/** True when `pathname` only matches the catch-all `*` route (or nothing). */
export function isCatchAllRoute(pathname: string, routes: RouteObject[]): boolean {
  const matches = matchRoutes(routes, pathname);
  if (!matches || matches.length === 0) return true;
  return matches[matches.length - 1].route.path === '*';
}

/**
 * Drop transactions for anonymous visitors on the catch-all route. The router
 * integration names those after the matched pattern, which ends in `*`.
 */
export function shouldDropTransaction(event: Event): boolean {
  if (!event.transaction?.endsWith('*')) return false;
  const userId = event.user?.id ?? Sentry.getIsolationScope().getUser()?.id;
  return !userId;
}

/** Starts session replay once; safe to call repeatedly. */
export function enableReplay(): void {
  if (!enabled || replayEnabled || Sentry.getReplay()) return;
  replayEnabled = true;
  Sentry.addIntegration(Sentry.replayIntegration());
}

/** Sets (or clears) the user on Sentry events, starting replay once known. */
export function setSentryUser(user: User | null): void {
  if (!enabled) return;
  Sentry.setUser(user ? { id: user.uid, email: user.email } : null);
  if (user) enableReplay();
}

/**
 * Initialises Sentry. Must run before the router is created so navigations
 * are instrumented from the first pageload.
 *
 * @param routes The data-router route table, to recognise catch-all pageloads.
 * @returns Whether Sentry was initialised (false when no DSN is configured).
 */
export function initSentry(routes: RouteObject[]): boolean {
  const env = import.meta.env;
  const dsn = env.VITE_SENTRY_DSN;
  if (!dsn) return false;

  Sentry.init({
    dsn,
    environment: env.VITE_SENTRY_ENVIRONMENT || 'development',
    integrations: [
      Sentry.reactRouterBrowserTracingIntegration({
        useLocation,
        useNavigationType,
        createRoutesFromChildren,
        matchRoutes,
      }),
    ],
    tracesSampleRate: parseSampleRate(
      env.VITE_SENTRY_TRACES_SAMPLE_RATE,
      DEFAULT_TRACES_SAMPLE_RATE,
    ),
    tracePropagationTargets: buildTracePropagationTargets(env.VITE_API_BASE_URL),
    replaysSessionSampleRate: parseSampleRate(
      env.VITE_SENTRY_REPLAYS_SESSION_SAMPLE_RATE,
      DEFAULT_REPLAYS_SESSION_SAMPLE_RATE,
    ),
    replaysOnErrorSampleRate: parseSampleRate(
      env.VITE_SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE,
      DEFAULT_REPLAYS_ON_ERROR_SAMPLE_RATE,
    ),
    beforeSendTransaction: (event) => (shouldDropTransaction(event) ? null : event),
  });
  enabled = true;

  // Anonymous visitors on `*` get no replay. Protected routes (including `*`)
  // redirect them to /login with a full page load, where replay starts; a
  // logged-in user on `*` gets replay via `setSentryUser`.
  if (!isCatchAllRoute(window.location.pathname, routes)) enableReplay();
  return true;
}
