import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import DebugBlockView from './DebugBlockView';
import { ServerRegistry } from '../markdown/serverRegistry';
import type { Block, BlockNoteEditor } from '@blocknote/core';

const makeBlock = (id: string, type = 'paragraph'): Block =>
  ({ id, type, props: {}, content: [], children: [] }) as unknown as Block;

function makeEditor(serializeResult = 'block content'): BlockNoteEditor {
  return {
    blocksToMarkdownLossy: vi.fn(() => serializeResult),
  } as unknown as BlockNoteEditor;
}

describe('DebugBlockView', () => {
  it('renders the panel header with block count', () => {
    const blocks = [makeBlock('b1'), makeBlock('b2')];
    render(<DebugBlockView blocks={blocks} editor={makeEditor()} registry={new ServerRegistry()} />);
    expect(screen.getByText(/Block structure \(2 blocks\)/)).toBeInTheDocument();
  });

  it('shows block index for each block', () => {
    const blocks = [makeBlock('b1'), makeBlock('b2')];
    render(<DebugBlockView blocks={blocks} editor={makeEditor()} registry={new ServerRegistry()} />);
    expect(screen.getByText('#0')).toBeInTheDocument();
    expect(screen.getByText('#1')).toBeInTheDocument();
  });

  it('shows block type in uppercase', () => {
    render(<DebugBlockView blocks={[makeBlock('b1', 'heading')]} editor={makeEditor()} registry={new ServerRegistry()} />);
    expect(screen.getByText('heading')).toBeInTheDocument();
  });

  it('shows "new" badge for unregistered blocks', () => {
    render(<DebugBlockView blocks={[makeBlock('b1')]} editor={makeEditor()} registry={new ServerRegistry()} />);
    expect(screen.getByText('new')).toBeInTheDocument();
  });

  it('shows "server" badge for registered blocks', () => {
    const registry = new ServerRegistry();
    registry.set('b1', { nodeId: 'n1', version: 3, nodeType: 'markdown' });
    render(<DebugBlockView blocks={[makeBlock('b1')]} editor={makeEditor()} registry={registry} />);
    expect(screen.getByText('server')).toBeInTheDocument();
  });

  it('shows shortened block id', () => {
    render(<DebugBlockView blocks={[makeBlock('abcdefgh-1234')]} editor={makeEditor()} registry={new ServerRegistry()} />);
    expect(screen.getByText(/bn: abcdefg/)).toBeInTheDocument();
  });

  it('shows node id and version for registered blocks', () => {
    const registry = new ServerRegistry();
    registry.set('b1', { nodeId: 'node-xyz-123', version: 5, nodeType: 'markdown' });
    render(<DebugBlockView blocks={[makeBlock('b1')]} editor={makeEditor()} registry={registry} />);
    expect(screen.getByText(/node: node-xyz/)).toBeInTheDocument();
    expect(screen.getByText(/v5/)).toBeInTheDocument();
  });

  it('shows serialized block content', () => {
    render(<DebugBlockView blocks={[makeBlock('b1')]} editor={makeEditor('# My heading')} registry={new ServerRegistry()} />);
    expect(screen.getByText('# My heading')).toBeInTheDocument();
  });

  it('shows (empty) placeholder for empty blocks', () => {
    render(<DebugBlockView blocks={[makeBlock('b1')]} editor={makeEditor('  ')} registry={new ServerRegistry()} />);
    expect(screen.getByText('(empty)')).toBeInTheDocument();
  });

  it('renders connector between blocks', () => {
    const blocks = [makeBlock('b1'), makeBlock('b2')];
    const { container } = render(
      <DebugBlockView blocks={blocks} editor={makeEditor()} registry={new ServerRegistry()} />,
    );
    expect(container.querySelectorAll('.debug-connector')).toHaveLength(1);
  });

  it('renders empty panel for zero blocks', () => {
    render(<DebugBlockView blocks={[]} editor={makeEditor()} registry={new ServerRegistry()} />);
    expect(screen.getByText(/Block structure \(0 blocks\)/)).toBeInTheDocument();
    expect(screen.queryByText('#0')).not.toBeInTheDocument();
  });
});
