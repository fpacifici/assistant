export interface ServerNodeState {
  nodeId: string;
  version: number;
  nodeType: string;
}

export class ServerRegistry {
  private map = new Map<string, ServerNodeState>();
  private deleted: string[] = [];

  set(blockId: string, state: ServerNodeState): void {
    this.map.set(blockId, state);
  }

  get(blockId: string): ServerNodeState | undefined {
    return this.map.get(blockId);
  }

  has(blockId: string): boolean {
    return this.map.has(blockId);
  }

  /** The editor block currently mapped to a server node, if any. */
  blockIdForNode(nodeId: string): string | undefined {
    for (const [blockId, state] of this.map) {
      if (state.nodeId === nodeId) return blockId;
    }
    return undefined;
  }

  markDeleted(blockId: string): void {
    const state = this.map.get(blockId);
    if (state) {
      this.deleted.push(state.nodeId);
      this.map.delete(blockId);
    }
  }

  consumeDeletedIds(): string[] {
    const ids = this.deleted;
    this.deleted = [];
    return ids;
  }

  clear(): void {
    this.map.clear();
    this.deleted = [];
  }

  updateVersion(blockId: string, version: number): void {
    const state = this.map.get(blockId);
    if (state) state.version = version;
  }
}
