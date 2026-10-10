import { describe, it, expect, beforeEach } from 'vitest';
import { colorSchemeOf, readPreference, resolveTheme, THEME_STORAGE_KEY, THEMES, writePreference } from './theme';

beforeEach(() => {
  localStorage.clear();
});

// --- resolveTheme ---

describe('resolveTheme', () => {
  it('follows the OS for the system preference', () => {
    expect(resolveTheme('system', true)).toBe('dark');
    expect(resolveTheme('system', false)).toBe('light');
  });

  it('lets an explicit preference win over the OS', () => {
    expect(resolveTheme('light', true)).toBe('light');
    expect(resolveTheme('dark', false)).toBe('dark');
    expect(resolveTheme('blossom', true)).toBe('blossom');
  });
});

// --- colorSchemeOf ---

describe('colorSchemeOf', () => {
  it('maps each theme to its light or dark base', () => {
    expect(colorSchemeOf('light')).toBe('light');
    expect(colorSchemeOf('dark')).toBe('dark');
    expect(colorSchemeOf('blossom')).toBe('light');
    expect(colorSchemeOf('sand')).toBe('light');
    expect(colorSchemeOf('ocean')).toBe('dark');
    expect(colorSchemeOf('twilight')).toBe('dark');
  });
});

// --- Storage ---

describe('readPreference / writePreference', () => {
  it('defaults to system', () => {
    expect(readPreference(localStorage)).toBe('system');
    expect(readPreference(null)).toBe('system');
  });

  it('round-trips an explicit preference', () => {
    writePreference(localStorage, 'dark');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
    expect(readPreference(localStorage)).toBe('dark');
  });

  it('round-trips every color theme', () => {
    for (const theme of THEMES) {
      writePreference(localStorage, theme);
      expect(readPreference(localStorage)).toBe(theme);
    }
  });

  it('clears the key for system', () => {
    writePreference(localStorage, 'light');
    writePreference(localStorage, 'system');
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it('ignores invalid stored values', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'sepia');
    expect(readPreference(localStorage)).toBe('system');
  });

  it('ignores storage failures', () => {
    const broken = {
      getItem: () => {
        throw new Error('denied');
      },
      setItem: () => {
        throw new Error('denied');
      },
    } as unknown as Storage;
    expect(readPreference(broken)).toBe('system');
    expect(() => writePreference(broken, 'dark')).not.toThrow();
  });
});
