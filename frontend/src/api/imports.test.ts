import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { runImport, uploadImportZip } from './imports';
import { ApiError } from './client';

class FakeXhr {
  static last: FakeXhr;
  method = '';
  url = '';
  withCredentials = false;
  responseType = '';
  status = 0;
  statusText = '';
  response: unknown = null;
  body: unknown = null;
  upload: { onprogress: ((e: Partial<ProgressEvent>) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor() {
    FakeXhr.last = this;
  }
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  send(body: unknown) {
    this.body = body;
  }
  respond(status: number, response: unknown) {
    this.status = status;
    this.response = response;
    this.onload?.();
  }
}

const mockFetch = vi.fn();

describe('imports API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('XMLHttpRequest', FakeXhr);
    vi.stubGlobal('fetch', mockFetch);
  });
  afterEach(() => vi.unstubAllGlobals());

  describe('uploadImportZip', () => {
    it('POSTs the file as multipart with credentials and reports progress', async () => {
      const onProgress = vi.fn();
      const file = new File(['zipdata'], 'export.zip', { type: 'application/zip' });

      const promise = uploadImportZip(file, onProgress);
      const xhr = FakeXhr.last;
      xhr.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 10 });
      xhr.respond(201, { import_id: 'imp-1' });

      await expect(promise).resolves.toBe('imp-1');
      expect(xhr.method).toBe('POST');
      expect(xhr.url).toContain('/imports');
      expect(xhr.withCredentials).toBe(true);
      expect((xhr.body as FormData).get('file')).toBe(file);
      expect(onProgress).toHaveBeenCalledWith(0.5);
    });

    it('rejects with the server detail on error', async () => {
      const promise = uploadImportZip(new File(['x'], 'x.zip'));
      FakeXhr.last.respond(413, { detail: 'Upload exceeds 100 bytes' });

      await expect(promise).rejects.toEqual(new ApiError(413, 'Upload exceeds 100 bytes'));
    });

    it('rejects on network error', async () => {
      const promise = uploadImportZip(new File(['x'], 'x.zip'));
      FakeXhr.last.onerror?.();

      await expect(promise).rejects.toBeInstanceOf(ApiError);
    });
  });

  describe('runImport', () => {
    it('POSTs include_web_clips to the run endpoint', async () => {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: () => Promise.resolve({ created: 1 }),
      } as Response);

      const report = await runImport('imp-1', { includeWebClips: true });

      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toContain('/imports/imp-1/run');
      expect(opts.method).toBe('POST');
      expect(JSON.parse(opts.body)).toEqual({ include_web_clips: true });
      expect(report).toEqual({ created: 1 });
    });
  });
});
