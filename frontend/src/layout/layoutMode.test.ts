import { describe, it, expect, beforeEach } from 'vitest';
import { modeForViewport, OVERRIDE_STORAGE_KEY, readOverride } from './layoutMode';

// --- modeForViewport ---

describe('modeForViewport', () => {
  it.each([
    [390, 844, 'mobile'], // phone portrait
    [844, 390, 'mobile'], // phone landscape
    [932, 430, 'mobile'], // large phone landscape
    [767, 1024, 'mobile'], // just under the width threshold
    [768, 1024, 'desktop'], // tablet portrait
    [1024, 768, 'desktop'], // tablet landscape
    [1366, 1024, 'desktop'], // large tablet
    [1440, 900, 'desktop'], // laptop
    [1200, 480, 'mobile'], // short window
  ] as const)('%i×%i → %s', (width, height, expected) => {
    expect(modeForViewport(width, height)).toBe(expected);
  });

  it('treats 500px of height as desktop and 499px as mobile', () => {
    expect(modeForViewport(1024, 500)).toBe('desktop');
    expect(modeForViewport(1024, 499)).toBe('mobile');
  });
});

// --- readOverride ---

describe('readOverride', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('returns null with no param and nothing stored', () => {
    expect(readOverride('', sessionStorage)).toBeNull();
  });

  it('stores and returns a forced mode', () => {
    expect(readOverride('?layout=mobile', sessionStorage)).toBe('mobile');
    expect(sessionStorage.getItem(OVERRIDE_STORAGE_KEY)).toBe('mobile');
    expect(readOverride('?layout=desktop', sessionStorage)).toBe('desktop');
    expect(sessionStorage.getItem(OVERRIDE_STORAGE_KEY)).toBe('desktop');
  });

  it('returns the stored mode when the param is absent', () => {
    readOverride('?layout=mobile', sessionStorage);
    expect(readOverride('?other=1', sessionStorage)).toBe('mobile');
  });

  it('clears the stored mode on layout=auto', () => {
    readOverride('?layout=mobile', sessionStorage);
    expect(readOverride('?layout=auto', sessionStorage)).toBeNull();
    expect(sessionStorage.getItem(OVERRIDE_STORAGE_KEY)).toBeNull();
    expect(readOverride('', sessionStorage)).toBeNull();
  });

  it('ignores unknown values', () => {
    expect(readOverride('?layout=tablet', sessionStorage)).toBeNull();
    readOverride('?layout=desktop', sessionStorage);
    expect(readOverride('?layout=tablet', sessionStorage)).toBe('desktop');
  });

  it('stores and returns the tui mode', () => {
    expect(readOverride('?layout=tui', sessionStorage)).toBe('tui');
    expect(readOverride('', sessionStorage)).toBe('tui');
    expect(readOverride('?layout=auto', sessionStorage)).toBeNull();
  });

  it('ignores a garbage stored value', () => {
    sessionStorage.setItem(OVERRIDE_STORAGE_KEY, 'weird');
    expect(readOverride('', sessionStorage)).toBeNull();
  });

  it('tolerates storage that throws', () => {
    const throwing = {
      getItem: () => {
        throw new Error('denied');
      },
      setItem: () => {
        throw new Error('denied');
      },
      removeItem: () => {
        throw new Error('denied');
      },
    } as unknown as Storage;
    expect(readOverride('?layout=mobile', throwing)).toBe('mobile');
    expect(readOverride('', throwing)).toBeNull();
    expect(readOverride('?layout=auto', throwing)).toBeNull();
  });

  it('works without storage', () => {
    expect(readOverride('?layout=desktop', null)).toBe('desktop');
    expect(readOverride('', null)).toBeNull();
  });
});
