import { describe, it, expect, beforeEach } from 'vitest';
import { readPreference, resolveTheme, THEME_STORAGE_KEY, writePreference } from './theme';

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
