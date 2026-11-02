import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { ChevronLeft, ChevronRight, ExternalLink, X } from "lucide-react";
import type { Source } from "@/lib/types";
import { typeLabel } from "@/lib/citations";
import { cn, formatDate } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import { useIsPhone, useIsWide } from "@/hooks/useMediaQuery";

interface PanelProps {
  sources: Source[];
  activeN: number;
  onSelect: (n: number) => void;
  onClose: () => void;
  onExplain?: (snippet: string) => void;
  /** show "Quiz me on this" (Ask only) */
  quiz?: boolean;
}

function Dl({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[88px_1fr] gap-x-3 gap-y-1.5 text-[13px]">
      {rows.map(([k, v]) => (<div key={k} className="contents"><dt className="text-muted">{k}</dt><dd className="min-w-0 break-words text-body-2">{v}</dd></div>))}
    </dl>
  );
}

function PanelBody({ sources, activeN, onSelect, onClose, onExplain, quiz }: PanelProps) {
  const navigate = useNavigate();
  const idx = Math.max(0, sources.findIndex((s) => s.n === activeN));
  const s = sources[idx];
  useEffect(() => {
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  if (!s) return null;
  const go = (d: number) => onSelect(sources[(idx + d + sources.length) % sources.length].n);
  return (
    <div className="flex h-full min-h-0 flex-col bg-surface text-ink">
      <div className="flex shrink-0 items-center justify-between px-5 pt-4">
        <span className="serif-label">Source {idx + 1} of {sources.length}</span>
        <div className="flex items-center gap-0.5">
          {sources.length > 1 && (
            <>
              <button type="button" aria-label="Previous source" onClick={() => go(-1)} className="rounded-full p-1.5 text-muted hover:bg-surface-2"><ChevronLeft size={18} strokeWidth={1.5} /></button>
              <button type="button" aria-label="Next source" onClick={() => go(1)} className="rounded-full p-1.5 text-muted hover:bg-surface-2"><ChevronRight size={18} strokeWidth={1.5} /></button>
            </>
          )}
          <button type="button" aria-label="Close sources" onClick={onClose} className="rounded-full p-1.5 text-muted hover:bg-surface-2"><X size={18} strokeWidth={1.5} /></button>
        </div>
      </div>
      <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto px-5 pb-4 pt-3">
        <h2 className="font-serif text-[24px] font-semibold leading-snug">{s.title}</h2>
        {s.subtitle && <p className="mt-0.5 text-[14px] text-muted">{s.subtitle.replace(", ", " · ")}</p>}
        <blockquote className="mt-4 rounded-lg bg-surface-2 px-4 py-3.5 font-serif text-[16px] leading-relaxed">{s.snippet}</blockquote>
        <div className="mt-4">
          <Dl rows={[
            ["Type", typeLabel(s.type)],
            ["Link", s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-accent underline underline-offset-2">Open <ExternalLink size={12} strokeWidth={1.75} aria-hidden /></a> : "Not public"],
            ...(s.license ? [["License", s.license] as [string, React.ReactNode]] : []),
            ...(s.retrieved_at ? [["Retrieved", formatDate(s.retrieved_at, { year: "numeric", month: "short", day: "numeric" })] as [string, React.ReactNode]] : []),
          ]} />
        </div>
      </div>
      <div className="shrink-0 border-t border-line px-5 py-4">
        {sources.length > 1 && (
          <>
            <p className="serif-label mb-1.5">In this answer</p>
            <ul className="mb-3 space-y-0.5">
              {sources.map((x) => (
                <li key={x.n}>
                  <button type="button" onClick={() => onSelect(x.n)} aria-current={x.n === s.n}
                    className={cn("flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-[14px] hover:bg-surface-2", x.n === s.n && "bg-surface-2")}>
                    <span className="w-4 shrink-0 text-center font-semibold text-accent">{x.n}</span>
                    <span className="truncate">{x.title}</span>
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
        {(onExplain || (quiz && s.lecture_id)) && (
          <div className="flex gap-2">
            {onExplain && <Button variant="outline" className="flex-1" onClick={() => { onExplain(s.snippet); onClose(); }}>Explain simpler</Button>}
            {quiz && s.lecture_id && (
              <Button variant="outline" className="flex-1" onClick={() => navigate("/quiz", { state: { autoBuild: { lecture_ids: [s.lecture_id], n: 5 } } })}>Quiz me on this</Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

/** Desktop: a 360 px column. Tablet: overlay sheet from the right. Phone: bottom sheet. */
export function SourcePanelHost({ open, ...rest }: PanelProps & { open: boolean }) {
  const wide = useIsWide();
  const phone = useIsPhone();
  if (wide) {
    return (
      <motion.aside initial={false} animate={{ width: open ? 360 : 0 }} transition={{ type: "spring", damping: 34, stiffness: 340 }}
        className="hidden shrink-0 overflow-hidden border-l border-line xl:block" aria-label="Source panel" aria-hidden={!open}>
        <div className="h-full w-[360px]">{open && <PanelBody {...rest} />}</div>
      </motion.aside>
    );
  }
  return (
    <Sheet open={open} onOpenChange={(o) => !o && rest.onClose()} side={phone ? "bottom" : "right"} title="Source" className={cn("bg-surface shadow-float", phone ? "h-[78dvh] rounded-t-2xl overflow-hidden" : "border-l border-line")}>
      <PanelBody {...rest} />
    </Sheet>
  );
}
