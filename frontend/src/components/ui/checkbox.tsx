import * as React from "react";
import * as C from "@radix-ui/react-checkbox";
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export const Checkbox = React.forwardRef<HTMLButtonElement, React.ComponentPropsWithoutRef<typeof C.Root>>(({ className, ...props }, ref) => (
  <C.Root ref={ref} className={cn("flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-[5px] border border-line-strong bg-surface data-[state=checked]:border-accent data-[state=checked]:bg-accent disabled:opacity-50", className)} {...props}>
    <C.Indicator><Check size={13} strokeWidth={2.5} className="text-accent-fg" /></C.Indicator>
  </C.Root>
));
Checkbox.displayName = "Checkbox";
