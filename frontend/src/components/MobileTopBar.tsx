/** Mobile header: [← back] [title] [actions] [⋯]. */

import { Link } from 'react-router';
import OverflowMenu from './OverflowMenu';
import { useTopBarSlotRef } from './TopBarSlot';

interface MobileTopBarProps {
  title: string;
  backTo?: string;
  /** Extra `⋯` menu entries (elements with `role="menuitem"`). */
  children?: React.ReactNode;
}

export default function MobileTopBar({ title, backTo, children }: MobileTopBarProps) {
  const slotRef = useTopBarSlotRef();
  return (
    <header className="mobile-topbar">
      {backTo ? (
        <Link to={backTo} className="topbar-btn topbar-back" aria-label="Back">
          &larr;
        </Link>
      ) : (
        <span className="topbar-spacer" />
      )}
      <h1 className="topbar-title">{title}</h1>
      <div className="topbar-actions" ref={slotRef} />
      <OverflowMenu>{children}</OverflowMenu>
    </header>
  );
}
