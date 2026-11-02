import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-[14px] font-medium transition-colors duration-150 disabled:opacity-50 disabled:pointer-events-none select-none",
  {
    variants: {
      variant: {
        primary: "bg-accent text-accent-fg hover:bg-accent-hover",
        outline: "border border-line-strong bg-surface text-ink hover:bg-surface-2",
        dark: "bg-user-bubble text-user-bubble-ink hover:opacity-90",
        cream: "bg-side-ink text-[#1E1A17] hover:bg-white shadow-float",
        ghost: "text-body-2 hover:bg-surface-2",
        link: "text-accent hover:underline underline-offset-2 rounded-md px-0 h-auto",
        danger: "border border-accent text-accent hover:bg-accent-soft",
      },
      size: { md: "h-10 px-4", sm: "h-8 px-3 text-[13px]", lg: "h-11 px-5", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof buttonVariants> {}
export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(({ className, variant, size, type = "button", ...props }, ref) => (
  <button ref={ref} type={type} className={cn(buttonVariants({ variant, size }), className)} {...props} />
));
Button.displayName = "Button";
