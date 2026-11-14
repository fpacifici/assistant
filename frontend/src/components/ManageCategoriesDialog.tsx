/**
 * Creates, renames, describes and deletes categories, from the Blogs and the
 * Reading tabs. Categories with no description are marked: the reading list's
 * AI reads the description to file links, so an empty one gets fewer links.
 */

import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  CATEGORIES_KEY,
  createCategory,
  deleteCategory,
  fetchCategories,
  updateCategory,
} from '../api/categories';
import ConfirmDialog from './ConfirmDialog';
import type { Category } from '../types';

/** Query prefixes that show categories or what is filed under them. */
const AFFECTED_KEYS = [CATEGORIES_KEY, ['blogs'], ['reading']] as const;

function useInvalidateCategories() {
  const queryClient = useQueryClient();
  return () =>
    Promise.all(
      AFFECTED_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey: [...queryKey] })),
    );
}

const DESCRIPTION_HINT = 'What belongs here, for example "papers and posts about database internals"';

interface CategoryFieldsProps {
  name: string;
  description: string;
  onName: (value: string) => void;
  onDescription: (value: string) => void;
  label: string;
}

function CategoryFields({ name, description, onName, onDescription, label }: CategoryFieldsProps) {
  return (
    <>
      <input
        aria-label={`${label} name`}
        placeholder="Name"
        maxLength={255}
        value={name}
        onChange={(e) => onName(e.target.value)}
      />
      <textarea
        aria-label={`${label} description`}
        placeholder={DESCRIPTION_HINT}
        rows={2}
        maxLength={2000}
        value={description}
        onChange={(e) => onDescription(e.target.value)}
      />
    </>
  );
}

function CategoryRow({ category }: { category: Category }) {
  const invalidate = useInvalidateCategories();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(category.name);
  const [description, setDescription] = useState(category.description ?? '');
  const [deleting, setDeleting] = useState(false);

  const save = useMutation({
    mutationFn: () => updateCategory(category.id, { name: name.trim(), description }),
    onSuccess: () => {
      void invalidate();
      setEditing(false);
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteCategory(category.id),
    onSuccess: invalidate,
  });

  if (editing) {
    return (
      <li className="category-row editing">
        <form
          className="category-form"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <CategoryFields
            label={category.name}
            name={name}
            description={description}
            onName={setName}
            onDescription={setDescription}
          />
          <p className="category-form-hint">A new description applies to new links only.</p>
          {save.isError && <p className="auth-error">{save.error.message}</p>}
          <div className="category-form-actions">
            <button type="submit" className="btn-secondary" disabled={!name.trim() || save.isPending}>
              Save
            </button>
            <button
              type="button"
              className="btn-cancel"
              onClick={() => {
                setName(category.name);
                setDescription(category.description ?? '');
                setEditing(false);
              }}
            >
              Cancel
            </button>
          </div>
        </form>
      </li>
    );
  }

  return (
    <li className="category-row">
      <div className="category-row-info">
        <div className="category-row-name">{category.name}</div>
        {category.description ? (
          <div className="category-row-description">{category.description}</div>
        ) : (
          <div className="category-row-description missing">No description</div>
        )}
      </div>
      <div className="category-row-actions">
        <button
          type="button"
          className="btn-secondary"
          aria-label={`Edit ${category.name}`}
          onClick={() => setEditing(true)}
        >
          Edit
        </button>
        <button
          type="button"
          className="btn-secondary"
          aria-label={`Delete ${category.name}`}
          onClick={() => setDeleting(true)}
        >
          Delete
        </button>
      </div>
      {remove.isError && <p className="auth-error">Could not delete this category.</p>}
      {deleting && (
        <ConfirmDialog
          message={`Delete the category "${category.name}"? Its blogs and links move to Unfiled.`}
          confirmLabel="Delete"
          onConfirm={() => {
            remove.mutate();
            setDeleting(false);
          }}
          onCancel={() => setDeleting(false)}
        />
      )}
    </li>
  );
}

function NewCategory() {
  const invalidate = useInvalidateCategories();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const create = useMutation({
    mutationFn: () => createCategory({ name: name.trim(), description }),
    onSuccess: () => {
      void invalidate();
      setName('');
      setDescription('');
    },
  });

  return (
    <form
      className="category-form"
      aria-label="New category"
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
    >
      <CategoryFields
        label="New category"
        name={name}
        description={description}
        onName={setName}
        onDescription={setDescription}
      />
      {create.isError && <p className="auth-error">{create.error.message}</p>}
      <div className="category-form-actions">
        <button type="submit" className="btn-secondary" disabled={!name.trim() || create.isPending}>
          Add category
        </button>
      </div>
    </form>
  );
}

export default function ManageCategoriesDialog({ onClose }: { onClose: () => void }) {
  const { data: categories = [], isPending } = useQuery({
    queryKey: [...CATEGORIES_KEY],
    queryFn: fetchCategories,
  });

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      // A confirmation open on top handles its own Escape.
      if (e.key === 'Escape' && !document.querySelector('.confirm-dialog')) onClose();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal manage-categories"
        role="dialog"
        aria-modal="true"
        aria-label="Manage categories"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h3>Manage categories</h3>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            &times;
          </button>
        </div>
        <NewCategory />
        {!isPending && categories.length === 0 && <p className="empty">No categories yet</p>}
        <ul className="category-rows">
          {categories.map((category) => (
            <CategoryRow key={category.id} category={category} />
          ))}
        </ul>
      </div>
    </div>
  );
}
