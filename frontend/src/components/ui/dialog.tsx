import * as React from "react";
import * as D from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";

export const Dialog = D.Root;
export const DialogTrigger = D.Trigger;
export const DialogClose = D.Close;

export function DialogContent({ className, children, title, description, hideClose, ...props }: Omit<React.ComponentPropsWithoutRef<typeof D.Content>, "title" | "description"> & { title: string; description?: string; hideClose?: boolean }) {
  return (
    <D.Portal>
      <D.Overlay className="fixed inset-0 z-50 bg-black/40 data-[state=open]:animate-in" />
      <D.Content
        className={cn("fixed left-1/2 top-1/2 z-50 w-[calc(100vw-32px)] max-w-md -translate-x-1/2 -translate-y-1/2 rounded-xl border border-line bg-surface p-6 shadow-float", className)}
        {...props}
      >
        <D.Title className="font-serif text-[20px] font-semibold text-ink">{title}</D.Title>
        {description ? <D.Description className="mt-1 text-[14px] text-muted">{description}</D.Description> : <D.Description className="sr-only">{title}</D.Description>}
        <div className="mt-4">{children}</div>
        {!hideClose && (
          <D.Close aria-label="Close" className="absolute right-3 top-3 rounded-full p-1.5 text-muted hover:bg-surface-2">
            <X size={16} strokeWidth={1.5} />
          </D.Close>
        )}
      </D.Content>
    </D.Portal>
  );
}
