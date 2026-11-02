import { Fragment, useEffect, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Check, ChevronDown, ExternalLink, X } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { EvidenceItem, QuizResults, ResultQuestion } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Notice, Skeleton } from "@/components/ui/misc";
import { cn } from "@/lib/utils";
import { QuizFrame } from "./shared";

/** Split `text` into pieces, marking the parts that equal one of the spans (case and whitespace tolerant). */
export function highlight(text: string, spans: string[]): { t: string; hit: boolean }[] {
  const ranges: [number, number][] = [];
  for (const raw of spans) {
    const span = raw.trim();
    if (!span) continue;
    const esc = span.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
    const m = new RegExp(esc, "i").exec(text);
    if (m) ranges.push([m.index, m.index + m[0].length]);
  }
  ranges.sort((a, b) => a[0] - b[0]);
  const merged: [number, number][] = [];
  for (const r of ranges) {
    const last = merged[merged.length - 1];
    if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]); else merged.push([...r]);
  }
  const out: { t: string; hit: boolean }[] = [];
  let at = 0;
  for (const [s, e] of merged) {
    if (s > at) out.push({ t: text.slice(at, s), hit: false });
    out.push({ t: text.slice(s, e), hit: true });
    at = e;
  }
  if (at < text.length) out.push({ t: text.slice(at), hit: false });
  return out.length ? out : [{ t: text, hit: false }];
}

function Evidence({ ev, spans }: { ev: EvidenceItem; spans: string[] }) {
  return (
    <li className="rounded-lg bg-surface-2 px-3.5 py-3">
      <div className="flex flex-wrap items-center gap-x-2 text-[13px]">
        <span className="font-medium text-ink">{ev.label}</span>
        <span className="text-muted">{ev.tier}</span>
        {ev.url && <a href={ev.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-accent underline underline-offset-2">Open <ExternalLink size={12} strokeWidth={1.75} aria-hidden /></a>}
        {ev.license && <span className="text-muted">{ev.license}</span>}
      </div>
      {ev.visible ? (
        <p className="mt-1.5 font-serif text-[15px] leading-relaxed">
          {highlight(ev.text, spans).map((p, i) => (p.hit ? <mark key={i} className="span-hit">{p.t}</mark> : <Fragment key={i}>{p.t}</Fragment>))}
        </p>
      ) : (
        <p className="mt-1.5 text-[13px] text-muted">This passage isn't shown because it is outside the material you can open.</p>
      )}
    </li>
  );
}

function QuestionCard({ q }: { q: ResultQuestion }) {
  const [open, setOpen] = useState(false);
  const alts = Object.entries(q.alternatives);
  return (
    <article className="rounded-xl border border-line bg-surface p-5">
      <div className="flex items-center justify-between gap-3">
        <span className="serif-label">Question {q.n}</span>
        <span className={cn("inline-flex h-7 items-center rounded-full px-3 text-[13px] font-medium", q.correct ? "bg-ok-soft text-ok" : "bg-accent-soft text-accent-soft-ink")}>{q.correct ? "Correct" : "Incorrect"}</span>
      </div>
      {q.stem && <p className="mt-3 text-[16px] leading-relaxed">{q.stem}</p>}
      <p className="mt-2 font-serif text-[18px] font-semibold leading-snug">{q.lead_in}</p>
      <ul className="mt-4 space-y-2">
        {q.options.map((o) => {
          const right = q.answer_ids.includes(o.id);
          const wrongPick = q.selected.includes(o.id) && !right;
          return (
            <li key={o.id} className={cn("flex items-start gap-3 rounded-lg border px-3.5 py-2.5 text-[15px]", right ? "border-ok bg-ok-soft/60" : wrongPick ? "border-accent bg-accent-soft/60" : "border-line")}>
              <span className="mt-[1px] flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-line-strong text-[12px] font-semibold">{o.id}</span>
              <span className={cn("min-w-0 flex-1", right && "font-medium text-ok", wrongPick && "text-accent")}>{o.text}</span>
              {right && <span className="flex shrink-0 items-center gap-1 text-[12px] font-medium text-ok"><Check size={15} strokeWidth={2} aria-hidden />Correct answer</span>}
              {wrongPick && <span className="flex shrink-0 items-center gap-1 text-[12px] font-medium text-accent"><X size={15} strokeWidth={2} aria-hidden />Your answer</span>}
              {q.selected.includes(o.id) && right && <span className="sr-only">You chose this</span>}
            </li>
          );
        })}
        {q.selected.length === 0 && <li className="text-[13px] text-muted">You didn't answer this question.</li>}
      </ul>
      <p className="mt-4 text-[15px] leading-relaxed">{q.explanation}</p>
      {alts.length > 0 && (
        <div className="mt-3">
          <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="inline-flex items-center gap-1.5 rounded-md text-[14px] text-body-2 hover:text-ink">
            Why not the others <ChevronDown size={14} strokeWidth={1.5} className={cn("transition-transform duration-200", open && "rotate-180")} aria-hidden />
          </button>
          {open && (
            <ul className="mt-2 space-y-1.5 text-[14px] text-body-2">
              {alts.map(([k, why]) => <li key={k} className="flex gap-2"><span className="w-4 shrink-0 font-semibold">{k}</span><span>{why}</span></li>)}
            </ul>
          )}
        </div>
      )}
      {q.evidence.length > 0 && (
        <div className="mt-4">
          <p className="serif-label mb-1.5">Evidence</p>
          <ul className="space-y-2">{q.evidence.map((e) => <Evidence key={e.id} ev={e} spans={q.spans.filter((s) => s.source_id === e.id).map((s) => s.span)} />)}</ul>
        </div>
      )}
      {q.label && <p className="mt-4 text-[12px] text-muted">{q.label}</p>}
    </article>
  );
}

export default function QuizResultsPage() {
  const { id = "" } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const given = (location.state as { results?: QuizResults } | null)?.results;
  const [r, setR] = useState<QuizResults | null>(given ?? null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    if (given && tries === 0) return;
    let live = true;
    setError(null);
    api.quizResults(id).then((x) => live && setR(x)).catch((e) => live && setError(errorMessage(e)));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, tries]);

  if (error) return <QuizFrame><Notice tone="error" action={<div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setTries((t) => t + 1)}>Try again</Button><Button size="sm" variant="outline" onClick={() => navigate("/quiz")}>Back to Quiz</Button></div>}>{error}</Notice></QuizFrame>;
  if (!r) return <QuizFrame wide><div className="space-y-4" aria-label="Loading results"><Skeleton className="h-14 w-40" />{[0, 1].map((i) => <Skeleton key={i} className="h-64 !rounded-xl" />)}</div></QuizFrame>;

  return (
    <QuizFrame wide>
      <p className="serif-label">Your result</p>
      <h1 className="font-serif text-[56px] font-semibold leading-none max-sm:text-[44px]">{r.score} of {r.length}</h1>
      <div className="mt-5 flex gap-2">
        <Button onClick={() => navigate("/quiz")}>New quiz</Button>
        <Button variant="outline" onClick={() => navigate("/quiz")}>Back to Quiz</Button>
      </div>
      <div className="mt-8 space-y-5">{r.questions.map((q) => <QuestionCard key={q.n} q={q} />)}</div>
    </QuizFrame>
  );
}
