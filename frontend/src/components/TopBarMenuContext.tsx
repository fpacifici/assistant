/** Registry that lets views deeper in the tree add entries to the mobile top bar's `⋯` menu. */

import { createContext, useCallback, useContext, useEffect, useId, useMemo, useState } from 'react';

export interface TopBarMenuItem {
  id: string;
  label: string;
  onSelect: () => void;
}

type Register = (owner: string, items: TopBarMenuItem[] | null) => void;

const RegisterContext = createContext<Register | null>(null);
const ItemsContext = createContext<TopBarMenuItem[]>([]);

export function TopBarMenuProvider({ children }: { children: React.ReactNode }) {
  const [byOwner, setByOwner] = useState<Record<string, TopBarMenuItem[]>>({});

  const register = useCallback<Register>((owner, items) => {
    setByOwner((prev) => {
      const next = { ...prev };
      if (items) next[owner] = items;
      else delete next[owner];
      return next;
    });
  }, []);

  const items = useMemo(() => Object.values(byOwner).flat(), [byOwner]);

  return (
    <RegisterContext.Provider value={register}>
      <ItemsContext.Provider value={items}>{children}</ItemsContext.Provider>
    </RegisterContext.Provider>
  );
}

/**
 * Add `items` to the `⋯` menu while the calling component is mounted.
 * `items` must be memoized by the caller. No-op outside a provider.
 */
// eslint-disable-next-line react-refresh/only-export-components
export function useTopBarMenuItems(items: TopBarMenuItem[]): void {
  const register = useContext(RegisterContext);
  const owner = useId();

  useEffect(() => {
    register?.(owner, items);
  }, [register, owner, items]);

  useEffect(() => () => register?.(owner, null), [register, owner]);
}

/** Entries registered via `useTopBarMenuItems`, in registration order. */
// eslint-disable-next-line react-refresh/only-export-components
export function useRegisteredMenuItems(): TopBarMenuItem[] {
  return useContext(ItemsContext);
}
