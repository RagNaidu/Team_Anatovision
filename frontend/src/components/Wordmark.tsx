import { cn } from "@/lib/utils";

export function Wordmark({ className, onDark, size = 24 }: { className?: string; onDark?: boolean; size?: number }) {
  return (
    <span className={cn("font-serif font-semibold leading-none tracking-tight", onDark ? "text-side-ink" : "text-ink", className)} style={{ fontSize: size }}>
      Anato<span className={onDark ? "text-side-logo" : "text-accent"}>Vision</span>
    </span>
  );
}
