/** List of a TUI pane: rows with a cursor bar (see `useListCursor`); a click activates a row. */

import { useEffect, useRef } from 'react';
import type { ReactNode } from 'react';

export default function TuiList<T extends { id: string }>({
  label,
  items,
  cursorIndex,
  openId,
  emptyText,
  onActivate,
  renderRow,
  footer,
}: {
  label: string;
  items: T[];
  cursorIndex: number;
  /** The item open in the URL; marked with ► */
  openId?: string;
  emptyText: string;
  onActivate: (item: T) => void;
  renderRow: (item: T) => ReactNode;
  /** Rendered after the rows (e.g. the infinite-scroll sentinel). */
  footer?: ReactNode;
}) {
  const listRef = useRef<HTMLUListElement>(null);
  const cursorItem = cursorIndex >= 0 ? items[cursorIndex] : undefined;

  useEffect(() => {
    listRef.current
      ?.querySelector('.tui-row.cursor')
      ?.scrollIntoView?.({ block: 'nearest' });
  }, [cursorItem?.id]);

  return (
    <ul
      ref={listRef}
      className="tui-list"
      role="listbox"
      aria-label={label}
      tabIndex={0}
      data-tui-focus
      aria-activedescendant={cursorItem ? `tui-row-${cursorItem.id}` : undefined}
    >
      {items.map((item, i) => (
        <li
          key={item.id}
          id={`tui-row-${item.id}`}
          role="option"
          aria-selected={i === cursorIndex}
          className={`tui-row${i === cursorIndex ? ' cursor' : ''}${item.id === openId ? ' open' : ''}`}
          onClick={() => onActivate(item)}
        >
          <span className="tui-row-mark" aria-hidden="true">{item.id === openId ? '►' : ' '}</span>
          <span className="tui-row-body">{renderRow(item)}</span>
        </li>
      ))}
      {items.length === 0 && <li className="tui-empty">{emptyText}</li>}
      {footer}
    </ul>
  );
}
