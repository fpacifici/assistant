import { apiFetch, ApiError } from './client';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export interface FileRecord {
  id: string;
  note_id: string;
  file_name: string;
  state: 'pending' | 'uploading' | 'complete' | 'expired';
  creation_timestamp: string;
}

export async function createFile(noteId: string, fileName: string): Promise<FileRecord> {
  return apiFetch<FileRecord>('/files', {
    method: 'POST',
    body: JSON.stringify({ note_id: noteId, file_name: fileName }),
  });
}

export async function uploadChunk(
  fileId: string,
  partNumber: number,
  data: ArrayBuffer,
): Promise<void> {
  const response = await fetch(`${BASE_URL}/files/${fileId}/parts/${partNumber}`, {
    method: 'PUT',
    body: data,
    credentials: 'include',
    headers: { 'Content-Type': 'application/octet-stream' },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail || response.statusText);
  }
}

export async function completeFile(fileId: string): Promise<FileRecord> {
  return apiFetch<FileRecord>(`/files/${fileId}`, { method: 'PATCH' });
}
