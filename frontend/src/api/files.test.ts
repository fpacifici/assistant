import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createFile, uploadChunk, completeFile } from './files';
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

const FILE_RECORD = {
  id: 'file-1',
  note_id: 'note-1',
  file_name: 'test.pdf',
  state: 'pending' as const,
  creation_timestamp: '2026-01-01T00:00:00Z',
};

describe('files API', () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => vi.restoreAllMocks());

  describe('createFile', () => {
    it('POSTs to /files with note_id and file_name', async () => {
      mockFetch.mockReturnValueOnce(okResponse(FILE_RECORD, 201));

      const result = await createFile('note-1', 'test.pdf');

      expect(mockFetch).toHaveBeenCalledOnce();
      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toContain('/files');
      expect(opts.method).toBe('POST');
      const body = JSON.parse(opts.body);
      expect(body).toMatchObject({ note_id: 'note-1', file_name: 'test.pdf' });
      expect(result).toEqual(FILE_RECORD);
    });

    it('throws ApiError on 403', async () => {
      mockFetch.mockReturnValueOnce(errResponse(403, 'Forbidden'));

      await expect(createFile('note-1', 'test.pdf')).rejects.toBeInstanceOf(ApiError);
    });

    it('sets credentials: include', async () => {
      mockFetch.mockReturnValueOnce(okResponse(FILE_RECORD, 201));
      await createFile('note-1', 'test.pdf');
      expect(mockFetch.mock.calls[0][1].credentials).toBe('include');
    });
  });

  describe('uploadChunk', () => {
    it('PUTs raw bytes to /files/{id}/parts/{n}', async () => {
      mockFetch.mockReturnValueOnce(okResponse(null, 204));

      const data = new ArrayBuffer(4);
      await uploadChunk('file-1', 2, data);

      expect(mockFetch).toHaveBeenCalledOnce();
      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toContain('/files/file-1/parts/2');
      expect(opts.method).toBe('PUT');
      expect(opts.body).toBe(data);
      expect(opts.headers['Content-Type']).toBe('application/octet-stream');
    });

    it('resolves without a value on 204', async () => {
      mockFetch.mockReturnValueOnce(okResponse(null, 204));
      const result = await uploadChunk('file-1', 1, new ArrayBuffer(0));
      expect(result).toBeUndefined();
    });

    it('throws ApiError on server error', async () => {
      mockFetch.mockReturnValueOnce(errResponse(500, 'Internal Server Error'));

      await expect(uploadChunk('file-1', 1, new ArrayBuffer(4))).rejects.toBeInstanceOf(ApiError);
    });

    it('throws ApiError with correct status on 410 (expired)', async () => {
      mockFetch.mockReturnValueOnce(errResponse(410, 'File expired'));

      const err = await uploadChunk('file-1', 1, new ArrayBuffer(4)).catch((e) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(410);
    });

    it('sets credentials: include', async () => {
      mockFetch.mockReturnValueOnce(okResponse(null, 204));
      await uploadChunk('file-1', 1, new ArrayBuffer(2));
      expect(mockFetch.mock.calls[0][1].credentials).toBe('include');
    });
  });

  describe('completeFile', () => {
    it('PATCHes /files/{id} and returns updated record', async () => {
      const completed = { ...FILE_RECORD, state: 'complete' as const };
      mockFetch.mockReturnValueOnce(okResponse(completed));

      const result = await completeFile('file-1');

      expect(mockFetch).toHaveBeenCalledOnce();
      const [url, opts] = mockFetch.mock.calls[0];
      expect(url).toContain('/files/file-1');
      expect(opts.method).toBe('PATCH');
      expect(result.state).toBe('complete');
    });

    it('throws ApiError on 409 (bad state transition)', async () => {
      mockFetch.mockReturnValueOnce(errResponse(409, 'File not in uploading state'));

      await expect(completeFile('file-1')).rejects.toBeInstanceOf(ApiError);
    });

    it('throws ApiError with correct status on 404', async () => {
      mockFetch.mockReturnValueOnce(errResponse(404, 'Not found'));

      const err = await completeFile('file-1').catch((e) => e);
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(404);
    });
  });
});
