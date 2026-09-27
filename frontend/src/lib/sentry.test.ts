import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Event } from '@sentry/react';
import { routes } from '../routes';

// Hoisted so every fresh import of `./sentry` sees the same mock functions.
const Sentry = vi.hoisted(() => ({
  init: vi.fn(),
  addIntegration: vi.fn(),
  replayIntegration: vi.fn(() => ({ name: 'Replay' })),
  getReplay: vi.fn(() => undefined),
  setUser: vi.fn(),
}));

vi.mock('@sentry/react', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@sentry/react')>()),
  ...Sentry,
}));

/** Fresh module per test: `initSentry` keeps module-level enabled/replay flags. */
async function loadSentryModule() {
  vi.resetModules();
  return import('./sentry');
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('parseSampleRate', () => {
  it('parses a valid rate', async () => {
    const { parseSampleRate } = await loadSentryModule();
    expect(parseSampleRate('0.25', 1)).toBe(0.25);
    expect(parseSampleRate('0', 1)).toBe(0);
    expect(parseSampleRate('1', 0.5)).toBe(1);
  });

  it('falls back when unset or empty', async () => {
    const { parseSampleRate } = await loadSentryModule();
    expect(parseSampleRate(undefined, 0.1)).toBe(0.1);
    expect(parseSampleRate('', 0.1)).toBe(0.1);
    expect(parseSampleRate('  ', 0.1)).toBe(0.1);
  });

  it('falls back on garbage or out-of-range values', async () => {
    const { parseSampleRate } = await loadSentryModule();
    expect(parseSampleRate('lots', 0.1)).toBe(0.1);
    expect(parseSampleRate('1.5', 0.1)).toBe(0.1);
    expect(parseSampleRate('-0.1', 0.1)).toBe(0.1);
    expect(parseSampleRate('Infinity', 0.1)).toBe(0.1);
  });
});

describe('buildTracePropagationTargets', () => {
  it('adds nothing for an empty or relative base URL', async () => {
    const { buildTracePropagationTargets } = await loadSentryModule();
    expect(buildTracePropagationTargets(undefined)).toEqual([]);
    expect(buildTracePropagationTargets('')).toEqual([]);
    expect(buildTracePropagationTargets('/api')).toEqual([]);
  });

  it('matches the API origin only', async () => {
    const { buildTracePropagationTargets } = await loadSentryModule();
    const [target] = buildTracePropagationTargets('http://localhost:8000');
    expect(target).toBeInstanceOf(RegExp);
    const re = target as RegExp;
    expect(re.test('http://localhost:8000/notebook/1')).toBe(true);
    expect(re.test('http://localhost:8000')).toBe(true);
    expect(re.test('http://localhost:80001')).toBe(false);
    expect(re.test('http://localhost:80001/notebook')).toBe(false);
    expect(re.test('http://evil.com/?http://localhost:8000/')).toBe(false);
  });
});

describe('isCatchAllRoute', () => {
  it('recognises real routes', async () => {
    const { isCatchAllRoute } = await loadSentryModule();
    expect(isCatchAllRoute('/notebooks/1/notes', routes)).toBe(false);
    expect(isCatchAllRoute('/login', routes)).toBe(false);
    expect(isCatchAllRoute('/', routes)).toBe(false);
  });

  it('flags paths only matched by the catch-all', async () => {
    const { isCatchAllRoute } = await loadSentryModule();
    expect(isCatchAllRoute('/wp-admin', routes)).toBe(true);
    expect(isCatchAllRoute('/notebooks/1/notes/2/extra', routes)).toBe(true);
  });

  it('treats no match at all as catch-all', async () => {
    const { isCatchAllRoute } = await loadSentryModule();
    expect(isCatchAllRoute('/anything', [{ path: '/login' }])).toBe(true);
  });
});

describe('shouldDropTransaction', () => {
  const transaction = (name: string, userId?: string): Event => ({
    type: 'transaction',
    transaction: name,
    ...(userId ? { user: { id: userId } } : {}),
  });

  it('drops anonymous catch-all transactions', async () => {
    const { shouldDropTransaction } = await loadSentryModule();
    expect(shouldDropTransaction(transaction('/*'))).toBe(true);
  });

  it('keeps catch-all transactions of logged-in users', async () => {
    const { shouldDropTransaction } = await loadSentryModule();
    expect(shouldDropTransaction(transaction('/*', 'u1'))).toBe(false);
  });

  it('keeps anonymous transactions on real routes', async () => {
    const { shouldDropTransaction } = await loadSentryModule();
    expect(shouldDropTransaction(transaction('/login'))).toBe(false);
    expect(
      shouldDropTransaction(transaction('/notebooks/:notebookId/notes/:noteId')),
    ).toBe(false);
  });
});

describe('initSentry', () => {
  it('does nothing without a DSN', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', '');
    const { initSentry, setSentryUser } = await loadSentryModule();

    expect(initSentry(routes)).toBe(false);
    setSentryUser({
      uid: 'u1',
      email: 'a@b.c',
      firstname: 'A',
      lastname: 'B',
      invite_quota_remaining: 0,
    });

    expect(Sentry.init).not.toHaveBeenCalled();
    expect(Sentry.setUser).not.toHaveBeenCalled();
    expect(Sentry.addIntegration).not.toHaveBeenCalled();
  });

  it('initialises with configured values and starts replay on real routes', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://key@o1.ingest.sentry.io/1');
    vi.stubEnv('VITE_SENTRY_ENVIRONMENT', 'production');
    vi.stubEnv('VITE_SENTRY_TRACES_SAMPLE_RATE', '0.5');
    vi.stubEnv('VITE_SENTRY_REPLAYS_SESSION_SAMPLE_RATE', 'garbage');
    vi.stubEnv('VITE_API_BASE_URL', 'http://localhost:8000');
    window.history.pushState({}, '', '/login');
    const { initSentry } = await loadSentryModule();

    expect(initSentry(routes)).toBe(true);

    expect(Sentry.init).toHaveBeenCalledOnce();
    const options = Sentry.init.mock.calls[0][0];
    expect(options.dsn).toBe('https://key@o1.ingest.sentry.io/1');
    expect(options.environment).toBe('production');
    expect(options.tracesSampleRate).toBe(0.5);
    expect(options.replaysSessionSampleRate).toBe(0.1);
    expect(options.replaysOnErrorSampleRate).toBe(1);
    expect(options.tracePropagationTargets).toHaveLength(1);
    expect(Sentry.addIntegration).toHaveBeenCalledOnce();
  });

  it('defers replay on the catch-all until a user is set', async () => {
    vi.stubEnv('VITE_SENTRY_DSN', 'https://key@o1.ingest.sentry.io/1');
    window.history.pushState({}, '', '/wp-admin');
    const { initSentry, setSentryUser } = await loadSentryModule();

    initSentry(routes);
    expect(Sentry.addIntegration).not.toHaveBeenCalled();

    const user = {
      uid: 'u1',
      email: 'a@b.c',
      firstname: 'A',
      lastname: 'B',
      invite_quota_remaining: 0,
    };
    setSentryUser(user);
    setSentryUser(user);

    expect(Sentry.setUser).toHaveBeenLastCalledWith({ id: 'u1', email: 'a@b.c' });
    expect(Sentry.addIntegration).toHaveBeenCalledOnce();

    setSentryUser(null);
    expect(Sentry.setUser).toHaveBeenLastCalledWith(null);
  });
});
