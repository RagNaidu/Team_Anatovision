import * as React from "react";
import * as P from "@radix-ui/react-popover";
import { cn } from "@/lib/utils";

export const Popover = P.Root;
export const PopoverTrigger = P.Trigger;
export const PopoverClose = P.Close;
export const PopoverContent = React.forwardRef<HTMLDivElement, React.ComponentPropsWithoutRef<typeof P.Content>>(({ className, sideOffset = 8, ...props }, ref) => (
  <P.Portal>
    <P.Content ref={ref} sideOffset={sideOffset} collisionPadding={12}
      className={cn("z-50 w-72 max-w-[calc(100vw-24px)] rounded-lg border border-line-strong bg-surface p-3 text-ink shadow-float", className)} {...props} />
  </P.Portal>
));
PopoverContent.displayName = "PopoverContent";
