import { createContext, useContext, type ReactNode } from "react";
import { createPortal } from "react-dom";

export const SlotContext = createContext<HTMLElement | null>(null);
/** Lets a page put its own list (for example the guide's station spine) into the sidebar. */
export function SidebarPortal({ children }: { children: ReactNode }) {
  const el = useContext(SlotContext);
  return el ? createPortal(children, el) : null;
}
