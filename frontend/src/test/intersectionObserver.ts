/** Fake `IntersectionObserver` (jsdom has none) whose intersections tests trigger by hand. */

import { act } from '@testing-library/react';

const observers = new Set<FakeIntersectionObserver>();

class FakeIntersectionObserver {
  readonly targets = new Set<Element>();

  constructor(private readonly callback: IntersectionObserverCallback) {
    observers.add(this);
  }

  observe(target: Element): void {
    this.targets.add(target);
  }

  unobserve(target: Element): void {
    this.targets.delete(target);
  }

  disconnect(): void {
    this.targets.clear();
    observers.delete(this);
  }

  takeRecords(): IntersectionObserverEntry[] {
    return [];
  }

  fire(target: Element): void {
    const entry = { target, isIntersecting: true } as IntersectionObserverEntry;
    this.callback([entry], this as unknown as IntersectionObserver);
  }
}

/** Install the fake on `window`; observers left from earlier tests are dropped. */
export function mockIntersectionObserver(): void {
  observers.clear();
  window.IntersectionObserver = FakeIntersectionObserver as unknown as typeof IntersectionObserver;
}

/** Report `target` as scrolled into view to every observer watching it. */
export function scrollIntoView(target: Element): void {
  act(() => {
    for (const observer of [...observers]) {
      if (observer.targets.has(target)) observer.fire(target);
    }
  });
}
