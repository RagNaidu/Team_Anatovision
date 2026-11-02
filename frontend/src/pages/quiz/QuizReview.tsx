import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { OpenQuiz } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Notice, PageTitle, Skeleton } from "@/components/ui/misc";
import { QuizFrame } from "./shared";

export default function QuizReview() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [quiz, setQuiz] = useState<OpenQuiz | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    let live = true;
    api.getQuiz(id).then((q) => live && setQuiz(q)).catch((e) => {
      if (!live) return;
      if (e instanceof ApiError && e.status === 409) { navigate(`/quiz/${id}/results`, { replace: true }); return; }
      setError(errorMessage(e));
    });
    return () => { live = false; };
  }, [id, tries, navigate]);

  async function submit() {
    setBusy(true); setSubmitError(null);
    try {
      const r = await api.submitQuiz(id);
      navigate(`/quiz/${id}/results`, { replace: true, state: { results: r } });
    } catch (e) { setSubmitError(errorMessage(e)); setBusy(false); setConfirm(false); }
  }

  if (error) return <QuizFrame><Notice tone="error" action={<Button size="sm" variant="outline" onClick={() => { setError(null); setTries((t) => t + 1); }}>Try again</Button>}>{error}</Notice></QuizFrame>;
  if (!quiz) return <QuizFrame><div className="space-y-3" aria-label="Loading"><Skeleton className="h-8 w-1/2" />{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12 !rounded-lg" />)}</div></QuizFrame>;

  const unanswered = quiz.questions.filter((_, i) => !(quiz.selections[String(i)]?.length)).length;
  return (
    <QuizFrame>
      <PageTitle sub={unanswered ? `${unanswered} not answered yet` : "All questions answered"}>Review your answers</PageTitle>
      <ul className="divide-y divide-line border-y border-line">
        {quiz.questions.map((q, i) => {
          const pick = quiz.selections[String(i)]?.[0];
          return (
            <li key={i} className="flex items-start gap-4 py-3.5">
              <span className="mt-0.5 w-6 shrink-0 font-serif text-[15px] italic text-muted">{i + 1}</span>
              <p className="min-w-0 flex-1 text-[15px] leading-snug">{q.lead_in || q.stem}</p>
              <span className={pick ? "shrink-0 text-[14px] font-medium text-body-2" : "shrink-0 text-[14px] text-accent"}>{pick ? `Answer ${pick}` : "Not answered"}</span>
              <Link to={`/quiz/${id}`} state={{ index: i }} className="shrink-0 text-[14px] text-accent underline underline-offset-2" aria-label={`Change answer to question ${i + 1}`}>Change</Link>
            </li>
          );
        })}
      </ul>
      {submitError && <Notice tone="error" className="mt-4">{submitError}</Notice>}
      <div className="mt-6 flex gap-2">
        <Button variant="outline" onClick={() => navigate(`/quiz/${id}`, { state: { index: quiz.questions.length - 1 } })}>Back to questions</Button>
        <Button onClick={() => setConfirm(true)} disabled={busy}>Submit quiz</Button>
      </div>
      <Dialog open={confirm} onOpenChange={setConfirm}>
        <DialogContent title="Submit this quiz?" description="Unanswered questions count as wrong.">
          <div className="flex justify-end gap-2">
            <DialogClose asChild><Button variant="outline">Keep working</Button></DialogClose>
            <Button onClick={() => void submit()} disabled={busy}>{busy ? "Submitting…" : "Submit"}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </QuizFrame>
  );
}
