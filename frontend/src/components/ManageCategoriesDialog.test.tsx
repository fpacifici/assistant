import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ManageCategoriesDialog from './ManageCategoriesDialog';
import { ApiError } from '../api/client';
import { renderWithProviders } from '../test/renderWithProviders';
import type { Category } from '../types';

vi.mock('../api/categories', () => ({
  CATEGORIES_KEY: ['categories'],
  fetchCategories: vi.fn(),
  createCategory: vi.fn(),
  updateCategory: vi.fn(),
  deleteCategory: vi.fn(),
}));

import {
  createCategory,
  deleteCategory,
  fetchCategories,
  updateCategory,
} from '../api/categories';

function category(fields: Partial<Category> = {}): Category {
  return {
    id: 'c1',
    name: 'Tech',
    description: 'Compilers and databases',
    created_at: '2026-10-01T00:00:00Z',
    ...fields,
  };
}

const onClose = vi.fn();

function render() {
  return renderWithProviders(<ManageCategoriesDialog onClose={onClose} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(fetchCategories).mockResolvedValue([
    category(),
    category({ id: 'c2', name: 'News', description: null }),
  ]);
  vi.mocked(deleteCategory).mockResolvedValue(undefined);
});

// --- Listing ---

describe('listing', () => {
  it('shows descriptions and marks the categories without one', async () => {
    render();
    expect(await screen.findByText('Compilers and databases')).toBeInTheDocument();
    const news = screen.getByText('News').closest('li')!;
    expect(within(news).getByText('No description')).toBeInTheDocument();
  });

  it('says when there are none', async () => {
    vi.mocked(fetchCategories).mockResolvedValue([]);
    render();
    expect(await screen.findByText('No categories yet')).toBeInTheDocument();
  });
});

// --- Creating ---

describe('creating', () => {
  it('adds a category with a description', async () => {
    vi.mocked(createCategory).mockResolvedValue(category({ id: 'c3', name: 'Papers' }));
    const user = userEvent.setup();
    render();

    await user.type(await screen.findByLabelText('New category name'), 'Papers');
    await user.type(screen.getByLabelText('New category description'), 'Research papers');
    await user.click(screen.getByRole('button', { name: 'Add category' }));

    await waitFor(() =>
      expect(createCategory).toHaveBeenCalledWith({
        name: 'Papers',
        description: 'Research papers',
      }),
    );
    await waitFor(() => expect(screen.getByLabelText('New category name')).toHaveValue(''));
  });

  it('shows a duplicate name error', async () => {
    vi.mocked(createCategory).mockRejectedValue(
      new ApiError(409, "A category named 'Tech' already exists"),
    );
    const user = userEvent.setup();
    render();

    await user.type(await screen.findByLabelText('New category name'), 'Tech');
    await user.click(screen.getByRole('button', { name: 'Add category' }));

    expect(await screen.findByText(/already exists/)).toBeInTheDocument();
  });

  it('needs a name', async () => {
    render();
    expect(await screen.findByRole('button', { name: 'Add category' })).toBeDisabled();
  });
});

// --- Editing ---

describe('editing', () => {
  it('renames and describes a category', async () => {
    vi.mocked(updateCategory).mockResolvedValue(category({ name: 'Science' }));
    const user = userEvent.setup();
    render();

    await user.click(await screen.findByRole('button', { name: 'Edit News' }));
    expect(screen.getByText(/applies to new links only/)).toBeInTheDocument();
    const name = screen.getByLabelText('News name');
    await user.clear(name);
    await user.type(name, 'Science');
    await user.type(screen.getByLabelText('News description'), 'Physics');
    await user.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() =>
      expect(updateCategory).toHaveBeenCalledWith('c2', {
        name: 'Science',
        description: 'Physics',
      }),
    );
  });
});

// --- Deleting ---

describe('deleting', () => {
  it('confirms before deleting, saying where the items go', async () => {
    const user = userEvent.setup();
    render();

    await user.click(await screen.findByRole('button', { name: 'Delete Tech' }));
    const confirm = screen.getByRole('alertdialog');
    expect(within(confirm).getByText(/blogs and links move to Unfiled/)).toBeInTheDocument();
    await user.click(within(confirm).getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(deleteCategory).toHaveBeenCalledWith('c1'));
  });

  it('Escape closes the confirmation, not the dialog', async () => {
    const user = userEvent.setup();
    render();

    await user.click(await screen.findByRole('button', { name: 'Delete Tech' }));
    await user.keyboard('{Escape}');

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
    await user.keyboard('{Escape}');
    expect(onClose).toHaveBeenCalled();
  });
});
