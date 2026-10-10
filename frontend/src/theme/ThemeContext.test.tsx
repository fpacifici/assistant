import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useTheme } from './ThemeContext';
import { THEME_STORAGE_KEY } from './theme';
import { ThemeSelect } from '../components/ThemeSwitcher';
import { renderWithProviders } from '../test/renderWithProviders';
import { mockViewport, setPrefersDark } from '../test/matchMedia';

function ThemeProbe() {
  const { theme, colorScheme, preference } = useTheme();
  return (
    <>
      <div data-testid="theme">{`${theme}/${preference}`}</div>
      <div data-testid="color-scheme">{colorScheme}</div>
    </>
  );
}

function renderProbe() {
  return renderWithProviders(
    <>
      <ThemeProbe />
      <ThemeSelect />
    </>,
  );
}

const originalMatchMedia = window.matchMedia;

beforeEach(() => {
  localStorage.clear();
  delete document.documentElement.dataset.theme;
  mockViewport(1440, 900);
});

afterEach(() => {
  window.matchMedia = originalMatchMedia;
  vi.restoreAllMocks();
});

// --- System preference ---

describe('system preference', () => {
  it('is light when the OS is light', () => {
    renderProbe();
    expect(screen.getByTestId('theme')).toHaveTextContent('light/system');
    expect(document.documentElement.dataset.theme).toBe('light');
  });

  it('is dark when the OS is dark', () => {
    setPrefersDark(true);
    renderProbe();
    expect(screen.getByTestId('theme')).toHaveTextContent('dark/system');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });

  it('follows OS changes live', () => {
    renderProbe();
    act(() => setPrefersDark(true));
    expect(screen.getByTestId('theme')).toHaveTextContent('dark/system');
    expect(document.documentElement.dataset.theme).toBe('dark');
  });
});

// --- Explicit preference ---

describe('explicit preference', () => {
  it('restores the stored preference', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    renderProbe();
    expect(screen.getByTestId('theme')).toHaveTextContent('dark/dark');
  });

  it('ignores OS changes', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light');
    renderProbe();
    act(() => setPrefersDark(true));
    expect(screen.getByTestId('theme')).toHaveTextContent('light/light');
  });

  it('is applied and persisted from the select', async () => {
    const user = userEvent.setup();
    renderProbe();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Theme' }), 'dark');
    expect(screen.getByTestId('theme')).toHaveTextContent('dark/dark');
    expect(document.documentElement.dataset.theme).toBe('dark');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

    await user.selectOptions(screen.getByRole('combobox', { name: 'Theme' }), 'system');
    expect(screen.getByTestId('theme')).toHaveTextContent('light/system');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it('applies a color theme with its base color scheme', async () => {
    const user = userEvent.setup();
    renderProbe();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Theme' }), 'blossom');
    expect(screen.getByTestId('theme')).toHaveTextContent('blossom/blossom');
    expect(screen.getByTestId('color-scheme')).toHaveTextContent('light');
    expect(document.documentElement.dataset.theme).toBe('blossom');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('blossom');

    await user.selectOptions(screen.getByRole('combobox', { name: 'Theme' }), 'ocean');
    expect(screen.getByTestId('color-scheme')).toHaveTextContent('dark');
    expect(document.documentElement.dataset.theme).toBe('ocean');
  });
});
