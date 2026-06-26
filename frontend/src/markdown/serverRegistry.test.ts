import { describe, it, expect, beforeEach } from 'vitest';
import { ServerRegistry } from './serverRegistry';

describe('ServerRegistry', () => {
  let registry: ServerRegistry;

  beforeEach(() => {
    registry = new ServerRegistry();
  });

  // --- set / get ---

  it('returns undefined for unknown block', () => {
    expect(registry.get('unknown')).toBeUndefined();
  });

  it('stores and retrieves state', () => {
    registry.set('block-1', { nodeId: 'node-a', version: 3, nodeType: 'markdown' });
    expect(registry.get('block-1')).toEqual({ nodeId: 'node-a', version: 3, nodeType: 'markdown' });
  });

  it('has() returns false for missing key', () => {
    expect(registry.has('x')).toBe(false);
  });

  it('has() returns true after set', () => {
    registry.set('block-1', { nodeId: 'node-a', version: 1, nodeType: 'markdown' });
    expect(registry.has('block-1')).toBe(true);
  });

  // --- updateVersion ---

  it('updateVersion changes only version', () => {
    registry.set('b', { nodeId: 'n', version: 1, nodeType: 'markdown' });
    registry.updateVersion('b', 5);
    expect(registry.get('b')).toEqual({ nodeId: 'n', version: 5, nodeType: 'markdown' });
  });

  it('updateVersion is a no-op for unknown block', () => {
    expect(() => registry.updateVersion('missing', 99)).not.toThrow();
  });

  // --- markDeleted / consumeDeletedIds ---

  it('consumeDeletedIds returns empty array when nothing deleted', () => {
    expect(registry.consumeDeletedIds()).toEqual([]);
  });

  it('markDeleted moves nodeId to deleted queue and removes from map', () => {
    registry.set('b', { nodeId: 'node-x', version: 1, nodeType: 'markdown' });
    registry.markDeleted('b');
    expect(registry.has('b')).toBe(false);
    expect(registry.consumeDeletedIds()).toEqual(['node-x']);
  });

  it('consumeDeletedIds drains the queue', () => {
    registry.set('b', { nodeId: 'node-x', version: 1, nodeType: 'markdown' });
    registry.markDeleted('b');
    registry.consumeDeletedIds();
    expect(registry.consumeDeletedIds()).toEqual([]);
  });

  it('markDeleted on unknown block does not enqueue anything', () => {
    registry.markDeleted('never-registered');
    expect(registry.consumeDeletedIds()).toEqual([]);
  });

  it('accumulates multiple deleted nodeIds', () => {
    registry.set('b1', { nodeId: 'n1', version: 1, nodeType: 'markdown' });
    registry.set('b2', { nodeId: 'n2', version: 1, nodeType: 'markdown' });
    registry.markDeleted('b1');
    registry.markDeleted('b2');
    expect(registry.consumeDeletedIds()).toEqual(expect.arrayContaining(['n1', 'n2']));
  });

  // --- clear ---

  it('clear resets the map and deleted queue', () => {
    registry.set('b', { nodeId: 'n', version: 1, nodeType: 'markdown' });
    registry.markDeleted('b');
    registry.clear();
    expect(registry.has('b')).toBe(false);
    expect(registry.consumeDeletedIds()).toEqual([]);
  });
});
