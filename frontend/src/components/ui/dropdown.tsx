import * as React from "react";
import * as M from "@radix-ui/react-dropdown-menu";
import { cn } from "@/lib/utils";

export const Menu = M.Root;
export const MenuTrigger = M.Trigger;
export const MenuContent = React.forwardRef<HTMLDivElement, React.ComponentPropsWithoutRef<typeof M.Content>>(({ className, sideOffset = 6, ...props }, ref) => (
  <M.Portal>
    <M.Content ref={ref} sideOffset={sideOffset} collisionPadding={12}
      className={cn("z-50 min-w-[170px] rounded-lg border border-line-strong bg-surface p-1 text-ink shadow-float", className)} {...props} />
  </M.Portal>
));
MenuContent.displayName = "MenuContent";
export const MenuItem = React.forwardRef<HTMLDivElement, React.ComponentPropsWithoutRef<typeof M.Item>>(({ className, ...props }, ref) => (
  <M.Item ref={ref} className={cn("flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-[14px] outline-none data-[highlighted]:bg-surface-2", className)} {...props} />
));
MenuItem.displayName = "MenuItem";
