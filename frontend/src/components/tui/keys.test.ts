import { describe, it, expect } from 'vitest';
import { digitFkey, nextPane, resolveKey } from './keys';
import type { KeyLike } from './keys';
import { moveIndex } from './listCursor';

function key(k: string, extra: Partial<KeyLike> = {}): KeyLike {
  return { key: k, code: '', altKey: false, ctrlKey: false, metaKey: false, shiftKey: false, ...extra };
}

// --- resolveKey ---

describe('resolveKey', () => {
  it('maps F1–F10 to function keys', () => {
    expect(resolveKey(key('F1'), { typing: false })).toEqual({ type: 'fkey', n: 1 });
    expect(resolveKey(key('F10'), { typing: true })).toEqual({ type: 'fkey', n: 10 });
  });

  it('ignores F11, F12 and modified F-keys', () => {
    expect(resolveKey(key('F11'), { typing: false })).toBeNull();
    expect(resolveKey(key('F5', { metaKey: true }), { typing: false })).toBeNull();
  });

  it('maps Alt+digit to function keys, Alt+0 to F10', () => {
    expect(resolveKey(key('¡', { altKey: true, code: 'Digit1' }), { typing: true })).toEqual({
      type: 'fkey',
      n: 1,
    });
    expect(resolveKey(key('º', { altKey: true, code: 'Digit0' }), { typing: false })).toEqual({
      type: 'fkey',
      n: 10,
    });
  });

  it('maps list and pane keys when not typing', () => {
    expect(resolveKey(key('ArrowDown'), { typing: false })).toEqual({ type: 'list', command: 'down' });
    expect(resolveKey(key('Enter'), { typing: false })).toEqual({ type: 'list', command: 'open' });
    expect(resolveKey(key('PageUp'), { typing: false })).toEqual({ type: 'list', command: 'pageUp' });
    expect(resolveKey(key('Tab'), { typing: false })).toEqual({ type: 'pane', to: 'next' });
    expect(resolveKey(key('Tab', { shiftKey: true }), { typing: false })).toEqual({
      type: 'pane',
      to: 'prev',
    });
    expect(resolveKey(key('ArrowLeft'), { typing: false })).toEqual({ type: 'pane', to: 'left' });
    expect(resolveKey(key('?'), { typing: false })).toEqual({ type: 'fkey', n: 1 });
  });

  it('leaves editing keys alone while typing', () => {
    for (const k of ['ArrowDown', 'Enter', 'Tab', 'ArrowLeft', '?', 'a']) {
      expect(resolveKey(key(k), { typing: true })).toBeNull();
    }
  });

  it('always takes Escape', () => {
    expect(resolveKey(key('Escape'), { typing: true })).toEqual({ type: 'escape' });
    expect(resolveKey(key('Escape'), { typing: false })).toEqual({ type: 'escape' });
  });

  it('leaves browser shortcuts alone', () => {
    expect(resolveKey(key('ArrowDown', { ctrlKey: true }), { typing: false })).toBeNull();
    expect(resolveKey(key('Enter', { metaKey: true }), { typing: false })).toBeNull();
  });
});

// --- digitFkey ---

describe('digitFkey', () => {
  it('maps digit codes, 0 to 10', () => {
    expect(digitFkey('Digit7')).toBe(7);
    expect(digitFkey('Digit0')).toBe(10);
    expect(digitFkey('KeyA')).toBeNull();
  });
});

// --- nextPane ---

describe('nextPane', () => {
  const all = ['notebooks', 'notes', 'editor'] as const;

  it('cycles with next / prev', () => {
    expect(nextPane('editor', 'next', [...all])).toBe('notebooks');
    expect(nextPane('notebooks', 'prev', [...all])).toBe('editor');
  });

  it('stops at the edges with left / right', () => {
    expect(nextPane('notebooks', 'left', [...all])).toBe('notebooks');
    expect(nextPane('notes', 'right', [...all])).toBe('editor');
    expect(nextPane('editor', 'right', [...all])).toBe('editor');
  });

  it('falls back to the first visible pane', () => {
    expect(nextPane('notebooks', 'next', ['notes', 'editor'])).toBe('notes');
  });
});

// --- moveIndex ---

describe('moveIndex', () => {
  it('moves and clamps', () => {
    expect(moveIndex(0, 'up', 5)).toBe(0);
    expect(moveIndex(0, 'down', 5)).toBe(1);
    expect(moveIndex(2, 'end', 5)).toBe(4);
    expect(moveIndex(4, 'home', 5)).toBe(0);
    expect(moveIndex(1, 'pageDown', 5)).toBe(4);
    expect(moveIndex(12, 'pageUp', 30)).toBe(2);
  });

  it('returns -1 for an empty list', () => {
    expect(moveIndex(0, 'down', 0)).toBe(-1);
  });
});
