import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import Layout from './Layout';
import { renderWithProviders } from '../test/renderWithProviders';
import { Route, Routes } from 'react-router';

vi.mock('./NotebookList', () => ({
  default: () => <div data-testid="notebook-list">NotebookList</div>,
}));

vi.mock('./NoteList', () => ({
  default: () => <div data-testid="note-list">NoteList</div>,
}));

vi.mock('./NoteEditor', () => ({
  default: () => <div data-testid="note-editor">NoteEditor</div>,
}));

function renderLayout(path: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/notebooks" element={<Layout />} />
      <Route path="/notebooks/:notebookId/notes" element={<Layout />} />
      <Route path="/notebooks/:notebookId/notes/:noteId" element={<Layout />} />
    </Routes>,
    { initialEntries: [path] },
  );
}

describe('Layout', () => {
  it('renders NotebookList always', () => {
    renderLayout('/notebooks');
    expect(screen.getByTestId('notebook-list')).toBeInTheDocument();
  });

  it('shows placeholder when no notebook is selected', () => {
    renderLayout('/notebooks');
    expect(screen.getByText('Select a notebook to get started')).toBeInTheDocument();
    expect(screen.queryByTestId('note-list')).not.toBeInTheDocument();
  });

  it('shows NoteList when notebook is selected', () => {
    renderLayout('/notebooks/nb-1/notes');
    expect(screen.getByTestId('note-list')).toBeInTheDocument();
    expect(screen.getByText('Select a note to edit')).toBeInTheDocument();
  });

  it('shows NoteEditor when note is selected', () => {
    renderLayout('/notebooks/nb-1/notes/note-1');
    expect(screen.getByTestId('note-editor')).toBeInTheDocument();
    expect(screen.getByTestId('note-list')).toBeInTheDocument();
  });
});
