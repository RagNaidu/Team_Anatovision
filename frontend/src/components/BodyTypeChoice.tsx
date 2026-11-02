import { useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import type { GuideBodyType } from "@/lib/types";
import { GUIDE_BODY_OPTIONS, bodyLabel } from "@/lib/bodyType";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

/** Asked first, when a guide is started or resumed without a saved choice. */
export function BodyTypeAsk({ onChoose }: { onChoose: (v: GuideBodyType) => void }) {
  return (
    <section aria-labelledby="bt-q" className="mt-8 rounded-xl border border-line bg-surface p-5">
      <h2 id="bt-q" className="font-serif text-[22px] font-semibold">What is the cadaver like?</h2>
      <p className="mt-1 text-[14px] text-muted">The guide's tips and checks are adjusted to this. You can change it any time from the station header.</p>
      <div role="radiogroup" aria-labelledby="bt-q" className="mt-4 grid gap-2 sm:grid-cols-2">
        {GUIDE_BODY_OPTIONS.map((o) => (
          <button key={o.value} type="button" role="radio" aria-checked={false} onClick={() => onChoose(o.value)}
            className="rounded-lg border border-line-strong bg-bone px-4 py-3 text-left transition-colors duration-150 hover:border-accent hover:bg-accent-soft">
            <span className="block text-[15px] font-medium">{o.label}</span>
            <span className="block text-[13px] text-muted">{o.hint}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

/** The station header chip: shows the choice and lets the student change it. */
export function BodyTypeChip({ value, onChange }: { value: GuideBodyType | null; onChange: (v: GuideBodyType) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger aria-label={`Body type: ${bodyLabel(value)}. Change`}
        className="inline-flex h-8 items-center gap-1.5 rounded-full border border-line-strong bg-surface px-3 text-[13px] text-body-2 transition-colors duration-150 hover:bg-surface-2">
        <span className="text-muted">Body type</span> <span className="font-medium text-ink">{bodyLabel(value)}</span> <ChevronDown size={14} strokeWidth={1.5} aria-hidden />
      </PopoverTrigger>
      <PopoverContent align="start" className="w-64 p-1.5">
        <ul role="radiogroup" aria-label="Body type">
          {GUIDE_BODY_OPTIONS.map((o) => (
            <li key={o.value}>
              <button type="button" role="radio" aria-checked={value === o.value} onClick={() => { onChange(o.value); setOpen(false); }}
                className={cn("flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left hover:bg-surface-2", value === o.value && "bg-surface-2")}>
                <Check size={15} strokeWidth={2} className={cn("mt-[3px] shrink-0 text-accent", value !== o.value && "invisible")} aria-hidden />
                <span><span className="block text-[14px]">{o.label}</span><span className="block text-[12px] text-muted">{o.hint}</span></span>
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  );
}
