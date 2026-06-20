import { apiFetch } from './client';
import type { User } from '../types';

export function fetchUsers(limit = 1): Promise<User[]> {
  return apiFetch<User[]>(`/user?limit=${limit}`);
}
