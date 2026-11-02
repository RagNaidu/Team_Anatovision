import { useMemo, useState } from "react";
import { ChevronDown, Lock, Search } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

export interface MultiOption { id: string; label: string; hint?: string; locked?: boolean }

/** A dropdown with search, a checkbox per option and "Select all". The trigger shows how many are chosen ("3 lectures"). */
export function MultiSelect({
  label, noun, nounPlural, options, value, onChange, emptyText,
}: { label: string; noun: string; nounPlural: string; options: MultiOption[]; value: string[]; onChange: (ids: string[]) => void; emptyText?: string }) {
  const [q, setQ] = useState("");
  const open = options.filter((o) => !o.locked);
  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? options.filter((o) => (o.label + " " + (o.hint ?? "")).toLowerCase().includes(t)) : options;
  }, [options, q]);
  const shownOpen = shown.filter((o) => !o.locked);
  const allShownChosen = shownOpen.length > 0 && shownOpen.every((o) => value.includes(o.id));
  const count = value.length;
  const summary = count === 0 ? `Choose ${nounPlural}` : `${count} ${count === 1 ? noun : nounPlural}`;

  function toggleAll() {
    const ids = new Set(shownOpen.map((o) => o.id));
    onChange(allShownChosen ? value.filter((v) => !ids.has(v)) : [...new Set([...value, ...ids])]);
  }

  return (
    <div>
      <p className="mb-1.5 text-[14px] font-medium text-body-2" id={`ms-${label}`}>{label}</p>
      <Popover onOpenChange={(o) => !o && setQ("")}>
        <PopoverTrigger aria-labelledby={`ms-${label}`} aria-label={`${label}: ${summary}`}
          className={cn("flex h-11 w-full items-center justify-between rounded-lg border bg-surface px-3.5 text-left text-[15px] transition-colors duration-150 hover:bg-surface-2",
            count ? "border-accent" : "border-line-strong")}>
          <span className={count ? "text-ink" : "text-muted"}>{summary}</span>
          <ChevronDown size={16} strokeWidth={1.5} className="text-muted" aria-hidden />
        </PopoverTrigger>
        <PopoverContent align="start" className="w-[min(420px,calc(100vw-32px))] p-0">
          <div className="border-b border-line p-2.5">
            <div className="relative">
              <Search size={15} strokeWidth={1.5} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
              <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Search ${nounPlural}`} aria-label={`Search ${nounPlural}`}
                className="h-9 w-full rounded-md border border-line-strong bg-bone pl-8 pr-2 text-[14px]" />
            </div>
            <div className="mt-2 flex items-center justify-between px-0.5 text-[13px]">
              <button type="button" onClick={toggleAll} disabled={shownOpen.length === 0} className="text-accent underline underline-offset-2 disabled:opacity-50">
                {allShownChosen ? "Clear all" : q.trim() ? "Select all shown" : "Select all"}
              </button>
              <span className="text-muted">{count} of {open.length} chosen</span>
            </div>
          </div>
          <ul className="scroll-quiet max-h-72 overflow-y-auto p-1.5" role="listbox" aria-multiselectable="true" aria-label={label}>
            {shown.length === 0 && <li className="px-2 py-3 text-[13px] text-muted">{emptyText ?? `No ${nounPlural} match.`}</li>}
            {shown.map((o) => (
              <li key={o.id} role="option" aria-selected={value.includes(o.id)}>
                <label className={cn("flex items-center gap-2.5 rounded-md px-2 py-2 text-[14px]", o.locked ? "cursor-not-allowed text-muted" : "cursor-pointer hover:bg-surface-2")}>
                  <Checkbox disabled={o.locked} checked={value.includes(o.id)} aria-label={o.label}
                    onCheckedChange={(c) => onChange(c === true ? [...value, o.id] : value.filter((v) => v !== o.id))} />
                  <span className="min-w-0 flex-1">{o.label}{o.hint && <span className="ml-1.5 text-muted">{o.hint}</span>}</span>
                  {o.locked && <span className="flex shrink-0 items-center gap-1 text-[12px]"><Lock size={12} strokeWidth={1.5} aria-hidden /> Ask your instructor</span>}
                </label>
              </li>
            ))}
          </ul>
        </PopoverContent>
      </Popover>
    </div>
  );
}
