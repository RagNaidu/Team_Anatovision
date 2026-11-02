import { cn } from "@/lib/utils";

/** Horizontal vertebra-style progress: one rounded segment per station. */
export function SpineBar({ count, current, furthest, label }: { count: number; current: number; furthest: number; label: string }) {
  return (
    <div className="flex gap-1" role="img" aria-label={label}>
      {Array.from({ length: count }).map((_, i) => (
        <span key={i} className={cn("h-2.5 flex-1 rounded-[5px] border transition-colors duration-200",
          i === current ? "border-accent bg-surface" : i < furthest ? "border-side-accent bg-side-accent" : "border-line-strong bg-transparent",
          i === current && "ring-2 ring-accent/25")} />
      ))}
    </div>
  );
}
