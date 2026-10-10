/** Mobile header: [← back] [title] [actions] [search] [⋯]. */

import { Link } from 'react-router';
import OverflowMenu from './OverflowMenu';
import { useTopBarSlotRef } from './TopBarSlot';

interface MobileTopBarProps {
  title: string;
  backTo?: string;
  /** Extra `⋯` menu entries (elements with `role="menuitem"`). */
  children?: React.ReactNode;
  /** Hide the search button (on the search page itself). */
  hideSearch?: boolean;
}

export default function MobileTopBar({ title, backTo, children, hideSearch = false }: MobileTopBarProps) {
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
      {!hideSearch && (
        <Link to="/search" className="topbar-btn topbar-search" aria-label="Search">
          &#x1F50D;&#xFE0E;
        </Link>
      )}
      <OverflowMenu>{children}</OverflowMenu>
    </header>
  );
}
