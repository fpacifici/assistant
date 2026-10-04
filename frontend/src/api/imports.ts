import { apiFetch, apiUrl, ApiError } from './client';

export interface KeptNote {
  note_id: string;
  notebook_id: string;
  title: string;
  notebook: string;
  source_path: string;
  imported_at: string | null;
  modified_at: string;
}

export interface DuplicateNote {
  title: string;
  notebook: string;
  source_path: string;
}

export interface FailedNote {
  source_path: string;
  error: string;
}

export interface FailedNotebook {
  name: string;
  reason: string;
  skipped_notes: number;
}

export interface ImportReport {
  notebooks_touched: number;
  created: number;
  refreshed: number;
  unchanged: number;
  skipped_web_clip: number;
  imported_web_clip: number;
  kept_modified: KeptNote[];
  kept_untracked: KeptNote[];
  duplicate_title: DuplicateNote[];
  failed: FailedNote[];
  notebooks_failed: FailedNotebook[];
}

/**
 * Upload an export zip; resolves to the import id to pass to `runImport`.
 *
 * Uses XMLHttpRequest rather than fetch because fetch cannot report upload
 * progress. `onProgress` receives a fraction between 0 and 1.
 */
export function uploadImportZip(
  file: File,
  onProgress?: (fraction: number) => void,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', apiUrl('/imports'));
    xhr.withCredentials = true;
    xhr.responseType = 'json';
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onload = () => {
      const body = xhr.response ?? {};
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(body.import_id);
      } else {
        reject(new ApiError(xhr.status, body.detail || xhr.statusText || 'Upload failed'));
      }
    };
    xhr.onerror = () => reject(new ApiError(0, 'Upload failed: network error'));
    const form = new FormData();
    form.append('file', file);
    xhr.send(form);
  });
}

export async function runImport(
  importId: string,
  opts: { includeWebClips: boolean },
): Promise<ImportReport> {
  return apiFetch<ImportReport>(`/imports/${importId}/run`, {
    method: 'POST',
    body: JSON.stringify({ include_web_clips: opts.includeWebClips }),
  });
}
