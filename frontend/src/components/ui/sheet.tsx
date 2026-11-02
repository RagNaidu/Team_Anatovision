import * as React from "react";
import * as D from "@radix-ui/react-dialog";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "@/lib/utils";

type Side = "left" | "right" | "bottom";
const OFFSCREEN: Record<Side, { x?: string; y?: string }> = { left: { x: "-100%" }, right: { x: "100%" }, bottom: { y: "100%" } };
const POS: Record<Side, string> = {
  left: "left-0 top-0 h-dvh w-[min(300px,88vw)]",
  right: "right-0 top-0 h-dvh w-[min(400px,92vw)]",
  bottom: "inset-x-0 bottom-0 max-h-[86dvh] rounded-t-2xl",
};

/** Drawer / overlay sheet / bottom sheet: Radix Dialog (focus trap, Esc, aria) with a gentle framer-motion spring. */
export function Sheet({
  open, onOpenChange, side, title, children, className, overlayClass,
}: { open: boolean; onOpenChange: (o: boolean) => void; side: Side; title: string; children: React.ReactNode; className?: string; overlayClass?: string }) {
  return (
    <D.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open && (
          <D.Portal forceMount>
            <D.Overlay asChild forceMount>
              <motion.div className={cn("fixed inset-0 z-40 bg-black/40", overlayClass)} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }} />
            </D.Overlay>
            <D.Content asChild forceMount aria-describedby={undefined}>
              <motion.div
                className={cn("fixed z-50 flex flex-col outline-none", POS[side], className)}
                initial={OFFSCREEN[side]} animate={{ x: 0, y: 0 }} exit={OFFSCREEN[side]}
                transition={{ type: "spring", damping: 32, stiffness: 340, mass: 0.9 }}
              >
                <D.Title className="sr-only">{title}</D.Title>
                {children}
              </motion.div>
            </D.Content>
          </D.Portal>
        )}
      </AnimatePresence>
    </D.Root>
  );
}
