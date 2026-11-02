import { pillLabel } from "@/lib/citations";
import { cn } from "@/lib/utils";
import type { Source } from "@/lib/types";
import { ArrowUpRight } from "lucide-react";

export function SourcesRow({ sources, activeN, onOpen }: { sources: Source[]; activeN?: number | null; onOpen: (n: number) => void }) {
  if (!sources.length) return null;
  return (
    <ul className="flex flex-wrap gap-2" aria-label="Sources">
      {sources.map((s) => (
        <li key={s.n}>
          <button type="button" onClick={() => onOpen(s.n)} aria-pressed={activeN === s.n}
            className={cn("inline-flex items-center gap-2 rounded-full border py-1 pl-1 pr-3 text-[13px] transition-colors duration-150",
              activeN === s.n ? "border-accent bg-accent-soft text-accent-soft-ink" : "border-line-strong bg-surface text-body-2 hover:bg-surface-2")}>
            <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent-soft-ink">{s.n}</span>
            <span>{pillLabel(s)}</span>
            {s.url && <ArrowUpRight size={12} strokeWidth={1.75} aria-hidden />}
          </button>
        </li>
      ))}
    </ul>
  );
}
