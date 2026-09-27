/** Portal slot that lets a view render buttons (e.g. Save) inside the mobile top bar. */

import { createContext, useContext, useState } from 'react';
import { createPortal } from 'react-dom';

type SetSlot = (el: HTMLElement | null) => void;

const SetSlotContext = createContext<SetSlot | null>(null);
const SlotContext = createContext<HTMLElement | null>(null);

export function TopBarSlotProvider({ children }: { children: React.ReactNode }) {
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  return (
    <SetSlotContext.Provider value={setSlot}>
      <SlotContext.Provider value={slot}>{children}</SlotContext.Provider>
    </SetSlotContext.Provider>
  );
}

/** Ref callback for the element that hosts `TopBarActions` content. */
// eslint-disable-next-line react-refresh/only-export-components
export function useTopBarSlotRef(): SetSlot | undefined {
  return useContext(SetSlotContext) ?? undefined;
}

/** Render `children` into the top bar's action slot; renders nothing when no slot is mounted. */
export function TopBarActions({ children }: { children: React.ReactNode }) {
  const slot = useContext(SlotContext);
  return slot ? createPortal(children, slot) : null;
}
