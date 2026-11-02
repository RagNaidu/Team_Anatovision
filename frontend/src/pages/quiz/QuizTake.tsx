import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { OpenQuiz } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Notice, Skeleton } from "@/components/ui/misc";
import { cn } from "@/lib/utils";
import { QuizFrame, SegBar, WebNote } from "./shared";

export default function QuizTake() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [quiz, setQuiz] = useState<OpenQuiz | null>(null);
  const [sel, setSel] = useState<Record<string, string[]>>({});
  const [cur, setCur] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    let live = true;
    setError(null);
    api.getQuiz(id).then((q) => {
      if (!live) return;
      setQuiz(q);
      setSel(q.selections ?? {});
      const fromReview = (location.state as { index?: number } | null)?.index;
      setCur(Math.min(fromReview ?? q.current ?? 0, q.questions.length - 1));
    }).catch((e) => {
      if (!live) return;
      // a submitted quiz has results, not questions
      if (e instanceof ApiError && e.status === 409) { navigate(`/quiz/${id}/results`, { replace: true }); return; }
      setError(errorMessage(e));
    });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, tries]);

  useEffect(() => { heading.current?.focus({ preventScroll: true }); }, [cur, quiz]);

  const goto = useCallback((i: number) => {
    setCur(i);
    void api.setCurrent(id, i).catch(() => undefined);
  }, [id]);

  async function choose(optionId: string) {
    const prev = sel[String(cur)];
    setSel((s) => ({ ...s, [String(cur)]: [optionId] }));
    setSaveError(null);
    try { await api.saveAnswer(id, cur, [optionId]); } catch (e) {
      setSel((s) => { const n = { ...s }; if (prev) n[String(cur)] = prev; else delete n[String(cur)]; return n; });
      setSaveError(`${errorMessage(e)} Your answer wasn't saved.`);
    }
  }

  if (error) return <QuizFrame><Notice tone="error" action={<div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setTries((t) => t + 1)}>Try again</Button><Button size="sm" variant="outline" onClick={() => navigate("/quiz")}>Back to Quiz</Button></div>}>{error}</Notice></QuizFrame>;
  if (!quiz) return <QuizFrame><div className="space-y-4" aria-label="Loading quiz"><Skeleton className="h-2 w-full" /><Skeleton className="h-4 w-1/4" /><Skeleton className="h-6 w-4/5" />{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-[52px] !rounded-xl" />)}</div></QuizFrame>;

  const q = quiz.questions[cur];
  const total = quiz.questions.length;
  const answered = (i: number) => (sel[String(i)]?.length ?? 0) > 0;
  const chosen = sel[String(cur)] ?? [];
  const last = cur === total - 1;

  return (
    <QuizFrame>
      <div className="mb-1"><SegBar length={total} answered={answered} current={cur} /></div>
      <p className="mt-2 text-[13px] text-muted">Question {cur + 1} of {total}</p>

      <AnimatePresence mode="wait" initial={false}>
        <motion.div key={cur} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }} className="mt-6">
          <h1 ref={heading} tabIndex={-1} className="sr-only outline-none">Question {cur + 1}</h1>
          {q.web && <WebNote note={q.source_note} />}
          {q.stem && <p className="mb-3 text-[16px] leading-relaxed">{q.stem}</p>}
          <p className="font-serif text-[19px] font-semibold leading-snug">{q.lead_in}</p>
          <div role="radiogroup" aria-label="Answer options" className="mt-5 space-y-2.5">
            {q.options.map((o) => {
              const on = chosen.includes(o.id);
              return (
                <button key={o.id} type="button" role="radio" aria-checked={on} onClick={() => void choose(o.id)}
                  className={cn("flex min-h-[52px] w-full items-center gap-3.5 rounded-xl border px-4 py-3 text-left text-[15px] transition-colors duration-150",
                    on ? "border-accent bg-accent-soft text-ink" : "border-line-strong bg-surface hover:bg-surface-2")}>
                  <span className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-full border text-[13px] font-semibold", on ? "border-accent bg-accent text-accent-fg" : "border-line-strong text-body-2")} aria-hidden>{o.id}</span>
                  <span className="min-w-0 flex-1">{o.text}</span>
                </button>
              );
            })}
          </div>
        </motion.div>
      </AnimatePresence>
      <div aria-live="polite" className="mt-3 min-h-[20px]">{saveError && <p role="alert" className="text-[13px] text-accent">{saveError}</p>}</div>

      <div className="mt-6 flex items-center justify-between gap-3">
        <Button variant="outline" onClick={() => goto(cur - 1)} disabled={cur === 0}><ArrowLeft size={15} strokeWidth={1.5} /> Back</Button>
        <nav aria-label="Jump to question" className="flex flex-wrap justify-center gap-1.5">
          {quiz.questions.map((_, i) => (
            <button key={i} type="button" onClick={() => goto(i)} aria-label={`Question ${i + 1}${answered(i) ? ", answered" : ""}`} aria-current={i === cur ? "step" : undefined}
              className={cn("h-7 w-7 rounded-full border text-[12px] transition-colors duration-150", answered(i) ? "border-accent bg-accent text-accent-fg" : "border-line-strong text-body-2 hover:bg-surface-2", i === cur && "ring-2 ring-accent/40 ring-offset-2 ring-offset-bone")}>
              {i + 1}
            </button>
          ))}
        </nav>
        {last ? <Button onClick={() => navigate(`/quiz/${id}/review`)}>Review answers</Button> : <Button onClick={() => goto(cur + 1)}>Next <ArrowRight size={15} strokeWidth={1.5} /></Button>}
      </div>
    </QuizFrame>
  );
}
