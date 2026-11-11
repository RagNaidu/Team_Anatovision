import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Menu as MenuIcon } from "lucide-react";
import { Sidebar } from "./Sidebar";
import { PreviewBar } from "./PreviewBar";
import { Wordmark } from "./Wordmark";
import { SlotContext } from "./SidebarSlot";
import { Sheet } from "@/components/ui/sheet";
import { useIsDesktop } from "@/hooks/useMediaQuery";

export function AppShell() {
  const isDesktop = useIsDesktop();
  const { pathname } = useLocation();
  const [drawer, setDrawer] = useState(false);
  const [slot, setSlot] = useState<HTMLElement | null>(null);
  useEffect(() => { setDrawer(false); }, [pathname]);
  useEffect(() => { if (isDesktop) setDrawer(false); }, [isDesktop]);
  const segment = pathname.split("/")[1] || "ask";

  return (
    <SlotContext.Provider value={slot}>
      {/* Fixed-height shell: the window never scrolls (overflow-hidden also clips absolutely positioned sr-only text that used to stretch the document), the sidebar keeps its place, and only <main> scrolls. */}
      <div className="relative flex h-screen flex-col overflow-hidden bg-bone supports-[height:100dvh]:h-dvh" data-testid="app-shell">
        <PreviewBar />
        <div className="flex min-h-0 flex-1 overflow-hidden">
          {isDesktop ? (
            <aside className="h-full min-h-0 w-[272px] shrink-0 overflow-hidden" data-testid="app-sidebar"><Sidebar slotRef={setSlot} /></aside>
          ) : (
            <Sheet open={drawer} onOpenChange={setDrawer} side="left" title="Menu"><Sidebar slotRef={setSlot} /></Sheet>
          )}
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">
            {!isDesktop && (
              <header className="flex h-12 shrink-0 items-center gap-3 border-b border-[rgb(var(--topline))] bg-bone px-3">
                <button type="button" aria-label="Open menu" onClick={() => setDrawer(true)} className="rounded-md p-2 text-body-2 hover:bg-surface-2">
                  <MenuIcon size={20} strokeWidth={1.5} />
                </button>
                <Wordmark size={20} />
              </header>
            )}
            <main className="scroll-quiet min-h-0 flex-1 overflow-y-auto overscroll-y-contain" id="main" data-testid="app-main">
              <AnimatePresence mode="wait" initial={false}>
                <motion.div key={segment} className="h-full" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
                  <Outlet />
                </motion.div>
              </AnimatePresence>
            </main>
          </div>
        </div>
      </div>
    </SlotContext.Provider>
  );
}
