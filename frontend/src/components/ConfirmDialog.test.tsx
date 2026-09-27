import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ConfirmDialog from './ConfirmDialog';

const onConfirm = vi.fn();
const onCancel = vi.fn();

function renderDialog() {
  return render(
    <ConfirmDialog
      message="Delete it?"
      confirmLabel="Delete"
      onConfirm={onConfirm}
      onCancel={onCancel}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ConfirmDialog', () => {
  it('renders the message as an alert dialog with focus on Cancel', () => {
    renderDialog();
    expect(screen.getByRole('alertdialog', { name: 'Delete it?' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Cancel' })).toHaveFocus();
  });

  it('calls onConfirm from the confirm button', async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByRole('button', { name: 'Delete' }));
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it('calls onCancel from the cancel button', async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(onCancel).toHaveBeenCalledOnce();
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it('cancels on Escape', async () => {
    const user = userEvent.setup();
    renderDialog();
    await user.keyboard('{Escape}');
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('cancels on a backdrop click but not a click inside', async () => {
    const user = userEvent.setup();
    const { container } = renderDialog();
    await user.click(screen.getByText('Delete it?'));
    expect(onCancel).not.toHaveBeenCalled();
    await user.click(container.querySelector('.modal-overlay')!);
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it('supports a custom cancel label', () => {
    render(
      <ConfirmDialog
        message="Discard?"
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByRole('button', { name: 'Keep editing' })).toBeInTheDocument();
  });
});
