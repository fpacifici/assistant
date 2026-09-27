import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import { useLayoutMode } from './LayoutModeContext';
import { OVERRIDE_STORAGE_KEY } from './layoutMode';
import { renderWithProviders } from '../test/renderWithProviders';
import { mockViewport, resizeViewport } from '../test/matchMedia';

function ModeProbe() {
  return <div data-testid="mode">{useLayoutMode()}</div>;
}

function renderProbe(path = '/') {
  return renderWithProviders(<ModeProbe />, { layout: 'auto', initialEntries: [path] });
}

const originalMatchMedia = window.matchMedia;

beforeEach(() => {
  sessionStorage.clear();
  delete document.documentElement.dataset.layout;
});

afterEach(() => {
  window.matchMedia = originalMatchMedia;
  vi.restoreAllMocks();
});

// --- Viewport detection ---

describe('viewport detection', () => {
  it('is mobile on a phone viewport', () => {
    mockViewport(390, 844);
    renderProbe();
    expect(screen.getByTestId('mode')).toHaveTextContent('mobile');
  });

  it('is desktop on a laptop viewport', () => {
    mockViewport(1440, 900);
    renderProbe();
    expect(screen.getByTestId('mode')).toHaveTextContent('desktop');
  });

  it('stays mobile when a phone rotates', () => {
    mockViewport(390, 844);
    renderProbe();
    act(() => resizeViewport(844, 390));
    expect(screen.getByTestId('mode')).toHaveTextContent('mobile');
    act(() => resizeViewport(390, 844));
    expect(screen.getByTestId('mode')).toHaveTextContent('mobile');
  });

  it('flips to mobile when the window narrows below 768px and back', () => {
    mockViewport(1024, 768);
    renderProbe();
    expect(screen.getByTestId('mode')).toHaveTextContent('desktop');
    act(() => resizeViewport(700, 768));
    expect(screen.getByTestId('mode')).toHaveTextContent('mobile');
    act(() => resizeViewport(1024, 768));
    expect(screen.getByTestId('mode')).toHaveTextContent('desktop');
  });

  it('defaults to desktop when matchMedia is unavailable', () => {
    // @ts-expect-error simulate an environment without matchMedia
    window.matchMedia = undefined;
    renderProbe();
    expect(screen.getByTestId('mode')).toHaveTextContent('desktop');
  });
});

// --- Override ---

describe('?layout= override', () => {
  it('forces mobile on a desktop viewport and persists across navigation', async () => {
    mockViewport(1440, 900);
    const { router } = renderProbe('/notebooks?layout=mobile');
    expect(screen.getByTestId('mode')).toHaveTextContent('mobile');

    await act(() => router.navigate('/notebooks/nb-1/notes'));
    expect(screen.getByTestId('mode')).toHaveTextContent('mobile');
    expect(sessionStorage.getItem(OVERRIDE_STORAGE_KEY)).toBe('mobile');
  });

  it('forces desktop on a phone viewport', () => {
    mockViewport(390, 844);
    renderProbe('/?layout=desktop');
    expect(screen.getByTestId('mode')).toHaveTextContent('desktop');
  });

  it('layout=auto clears the override', async () => {
    mockViewport(1440, 900);
    const { router } = renderProbe('/?layout=mobile');
    await act(() => router.navigate('/?layout=auto'));
    expect(screen.getByTestId('mode')).toHaveTextContent('desktop');
    await act(() => router.navigate('/notebooks'));
    expect(screen.getByTestId('mode')).toHaveTextContent('desktop');
  });

  it('ignores unknown values', () => {
    mockViewport(1440, 900);
    renderProbe('/?layout=tablet');
    expect(screen.getByTestId('mode')).toHaveTextContent('desktop');
  });

  it('tolerates session storage throwing', () => {
    mockViewport(1440, 900);
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('denied');
    });
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    renderProbe('/?layout=mobile');
    expect(screen.getByTestId('mode')).toHaveTextContent('mobile');
  });
});

// --- data-layout attribute ---

describe('data-layout attribute', () => {
  it('reflects the resolved mode on the document element', () => {
    mockViewport(1024, 768);
    renderProbe();
    expect(document.documentElement.dataset.layout).toBe('desktop');
    act(() => resizeViewport(390, 844));
    expect(document.documentElement.dataset.layout).toBe('mobile');
  });

  it('reflects a forced mode', () => {
    renderWithProviders(<ModeProbe />, { layout: 'mobile' });
    expect(document.documentElement.dataset.layout).toBe('mobile');
  });
});
