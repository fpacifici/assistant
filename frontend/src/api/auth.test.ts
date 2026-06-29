import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { register, login, logout, getMe } from './auth';
import { ApiError } from './client';

const mockFetch = vi.fn();
vi.stubGlobal('fetch', mockFetch);

function okResponse(body: unknown, status = 200) {
  return Promise.resolve({
    ok: true,
    status,
    json: () => Promise.resolve(body),
  } as Response);
}

function errResponse(status: number, detail: string) {
  return Promise.resolve({
    ok: false,
    status,
    statusText: 'Error',
    json: () => Promise.resolve({ detail }),
  } as Response);
}

const USER = { uid: 'u1', email: 'a@b.com', firstname: 'A', lastname: 'B' };

describe('auth API', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.restoreAllMocks());

  describe('register', () => {
    it('POSTs to /auth/register and returns the user', async () => {
      mockFetch.mockReturnValueOnce(okResponse(USER, 201));

      const result = await register({ email: 'a@b.com', password: 'pw', firstname: 'A', lastname: 'B' });

      expect(mockFetch).toHaveBeenCalledOnce();
      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toContain('/auth/register');
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toMatchObject({ email: 'a@b.com' });
      expect(result).toEqual(USER);
    });

    it('throws ApiError on 409', async () => {
      mockFetch.mockReturnValueOnce(errResponse(409, 'Email already registered'));

      await expect(register({ email: 'a@b.com', password: 'pw', firstname: 'A', lastname: 'B' }))
        .rejects.toBeInstanceOf(ApiError);
    });
  });

  describe('login', () => {
    it('POSTs to /auth/login and returns the user', async () => {
      mockFetch.mockReturnValueOnce(okResponse(USER));

      const result = await login({ email: 'a@b.com', password: 'pw' });

      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toContain('/auth/login');
      expect(opts.method).toBe('POST');
      expect(result).toEqual(USER);
    });

    it('throws ApiError with status 401 on bad credentials', async () => {
      mockFetch.mockReturnValueOnce(errResponse(401, 'Invalid credentials'));

      const err = await login({ email: 'a@b.com', password: 'wrong' }).catch(e => e);
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(401);
    });
  });

  describe('logout', () => {
    it('POSTs to /auth/logout', async () => {
      mockFetch.mockReturnValueOnce(okResponse(null, 204));

      await logout();

      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toContain('/auth/logout');
      expect(opts.method).toBe('POST');
    });
  });

  describe('getMe', () => {
    it('GETs /auth/me and returns the user', async () => {
      mockFetch.mockReturnValueOnce(okResponse(USER));

      const result = await getMe();

      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toContain('/auth/me');
      expect(opts?.method).toBeUndefined();
      expect(result).toEqual(USER);
    });

    it('throws ApiError with status 401 when unauthenticated', async () => {
      mockFetch.mockReturnValueOnce(errResponse(401, 'Authentication required'));

      const err = await getMe().catch(e => e);
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(401);
    });
  });

  it('sets credentials: include on every request', async () => {
    mockFetch.mockReturnValue(okResponse(USER));
    await getMe();
    expect(mockFetch.mock.calls[0][1].credentials).toBe('include');
  });
});
