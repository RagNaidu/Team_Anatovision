import { cn } from "@/lib/utils";

export function CitationChip({ n, active, onClick }: { n: number; active?: boolean; onClick?: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`Source ${n}`}
      aria-pressed={Boolean(active)}
      className={cn(
        "cite mx-[2px] inline-flex h-[20px] min-w-[20px] -translate-y-[1px] items-center justify-center rounded-full px-1.5 align-middle text-[11px] font-semibold leading-none transition-colors duration-150",
        active ? "bg-accent text-accent-fg" : "bg-accent-soft text-accent-soft-ink hover:bg-accent hover:text-accent-fg",
      )}
    >
      {n}
    </button>
  );
}
