import { useId, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, ChevronDown } from "lucide-react";
import { cn, seconds } from "@/lib/utils";
import type { StageView } from "@/hooks/useAskProgress";

/**
 * The waiting indicator. While waiting: three quiet dots (CSS, 1.4 s) and, only if the backend really reports stages, a chevron that
 * expands into the real stages. When finished it shrinks to a tiny muted "6 s" (with the chevron if there are stages to show).
 * `label` is for the quiz build and the guide check, which have their own words; the Ask answer shows no words.
 */
export function ProgressRow({
  phase, label, stages, totalMs, className,
}: { phase: "waiting" | "done"; label?: string; stages?: StageView[]; totalMs?: number; className?: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const expandable = Boolean(stages && stages.length > 0);
  const dots = (
    <span className="inline-flex items-center gap-1" aria-hidden>
      <span className="wait-dot" /><span className="wait-dot" /><span className="wait-dot" />
    </span>
  );
  const head =
    phase === "waiting" ? (
      <>
        {dots}
        {label ? <span className="text-[14px] text-muted">{label}</span> : <span className="sr-only">Preparing the answer</span>}
      </>
    ) : (
      <span className="text-[12px] text-muted">{totalMs !== undefined ? seconds(totalMs) : "Done"}</span>
    );

  return (
    <div className={cn("text-muted", className)}>
      {expandable ? (
        <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}
          className="-ml-1 inline-flex items-center gap-2 rounded-md px-1 py-1 hover:text-body-2">
          {head}
          <ChevronDown size={14} strokeWidth={1.5} className={cn("transition-transform duration-200", open && "rotate-180")} aria-hidden />
          {phase === "done" && <span className="sr-only">Show the steps taken</span>}
        </button>
      ) : (
        <div role="status" className="inline-flex items-center gap-2 py-1">{head}</div>
      )}
      <AnimatePresence initial={false}>
        {expandable && open && (
          <motion.ul id={id} initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }} className="overflow-hidden">
            <div className="space-y-1.5 pb-1 pt-1.5">
              {stages!.map((s) => (
                <li key={s.key} className="flex items-center gap-2 text-[13px]">
                  {s.state === "done" ? (
                    <Check size={13} strokeWidth={2} className="text-ok" aria-label="done" />
                  ) : (
                    <span className="stage-pulse mx-[3px] h-[7px] w-[7px] rounded-full bg-accent" aria-label="in progress" />
                  )}
                  <span className={cn(s.state === "current" ? "stage-pulse text-body-2" : "text-body-2")}>{s.label}</span>
                  {s.state === "done" && s.seconds !== null && <span className="text-[12px] text-muted">{s.seconds < 10 ? s.seconds.toFixed(1) : Math.round(s.seconds)} s</span>}
                </li>
              ))}
            </div>
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
