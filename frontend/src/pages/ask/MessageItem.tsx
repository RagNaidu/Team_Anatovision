import { useState } from "react";
import { motion } from "framer-motion";
import { Check, Copy, Flag, Info, RotateCcw } from "lucide-react";
import type { Message } from "@/lib/types";
import type { StageView } from "@/hooks/useAskProgress";
import { AnswerMarkdown } from "./AnswerMarkdown";
import { SourcesRow } from "./SourcesRow";
import { FlagDialog } from "./FlagDialog";
import { ProgressRow } from "@/components/ProgressRow";
import { Button } from "@/components/ui/button";

const rise = { initial: { opacity: 0, y: 8 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.2, ease: "easeOut" as const } };

export function UserMessage({ message, animate = true }: { message: Message; animate?: boolean }) {
  return (
    <motion.div {...(animate ? rise : {})} className="flex justify-end">
      <p className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl bg-user-bubble px-4 py-2.5 text-[15px] text-user-bubble-ink">{message.markdown}</p>
    </motion.div>
  );
}

export function AssistantMessage({
  message, fresh, stages, activeN, onOpenSource, onRetry, animate = true,
}: {
  message: Message; fresh?: boolean; stages?: StageView[]; activeN?: number | null; animate?: boolean;
  onOpenSource: (messageId: string, n: number) => void; onRetry?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const [flagOpen, setFlagOpen] = useState(false);
  const calm = message.kind === "not_covered" || message.kind === "refused";
  const isError = message.kind === "error";
  const cur = (n: number) => onOpenSource(message.id, n);

  async function copy() {
    try { await navigator.clipboard.writeText(message.markdown.replace(/\s?\[\d+\]/g, "")); setCopied(true); setTimeout(() => setCopied(false), 1600); } catch { /* clipboard can be blocked */ }
  }

  return (
    <motion.article {...(animate ? rise : {})} aria-label="Answer" className="group">
      {fresh && message.timing_ms > 0 && <ProgressRow phase="done" totalMs={message.timing_ms} stages={stages} className="mb-2" />}
      {calm || isError ? (
        <div role={isError ? "alert" : undefined} className="flex items-start gap-3 rounded-xl border border-line bg-surface px-4 py-3.5">
          <Info size={18} strokeWidth={1.5} className="mt-[3px] shrink-0 text-muted" aria-hidden />
          <div className="min-w-0 flex-1">
            <div className="text-[15px] leading-relaxed text-ink">{message.markdown || "Something went wrong. Please try again."}</div>
            {isError && onRetry && <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}><RotateCcw size={14} strokeWidth={1.5} /> Try again</Button>}
          </div>
        </div>
      ) : (
        <AnswerMarkdown markdown={message.markdown} sources={message.sources} activeN={activeN} onCite={cur} reveal={fresh} />
      )}
      {!calm && !isError && message.sources.length > 0 && <div className="mt-4"><SourcesRow sources={message.sources} activeN={activeN} onOpen={cur} /></div>}
      {message.footer && (message.footer.basis_line || message.footer.access_note) && (
        <div className="mt-3 space-y-0.5 text-[13px] text-muted">
          {message.footer.basis_line && <p>{message.footer.basis_line}</p>}
          {message.footer.access_note && <p>{message.footer.access_note}</p>}
        </div>
      )}
      {!calm && !isError && (
        <div className="mt-2 flex items-center gap-1 text-[13px] text-muted">
          <button type="button" onClick={() => void copy()} className="-ml-2 inline-flex items-center gap-1.5 rounded-md px-2 py-1 hover:bg-surface-2 hover:text-body-2">
            {copied ? <Check size={14} strokeWidth={1.75} /> : <Copy size={14} strokeWidth={1.5} />} {copied ? "Copied" : "Copy"}
          </button>
          <button type="button" onClick={() => setFlagOpen(true)} className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 hover:bg-surface-2 hover:text-body-2">
            <Flag size={14} strokeWidth={1.5} /> Flag
          </button>
          <FlagDialog messageId={message.id} open={flagOpen} onOpenChange={setFlagOpen} />
        </div>
      )}
    </motion.article>
  );
}
