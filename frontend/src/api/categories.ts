import { apiFetch } from './client';
import type { Category } from '../types';

/** Query key of the category list, shared by the Blogs and Reading tabs. */
export const CATEGORIES_KEY = ['categories'] as const;

export function fetchCategories(): Promise<Category[]> {
  return apiFetch<Category[]>('/category');
}

export interface CategoryInput {
  name: string;
  /** Blank or missing clears it. */
  description?: string | null;
}

export function createCategory(input: CategoryInput): Promise<Category> {
  return apiFetch<Category>('/category', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

/** Rename and describe a category. Nothing already filed is re-categorized. */
export function updateCategory(id: string, input: CategoryInput): Promise<Category> {
  return apiFetch<Category>(`/category/${id}`, {
    method: 'PUT',
    body: JSON.stringify(input),
  });
}

/** Delete a category. Its blogs and links move to Unfiled. */
export function deleteCategory(id: string): Promise<void> {
  return apiFetch<void>(`/category/${id}`, { method: 'DELETE' });
}
