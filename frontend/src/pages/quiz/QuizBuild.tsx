import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { BuildResult, QuizJob } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Notice, PageTitle } from "@/components/ui/misc";
import { ProgressRow } from "@/components/ProgressRow";
import { QuizFrame, lastBuild, rememberBuild } from "./shared";

export default function QuizBuild() {
  const { jobId = "" } = useParams();
  const navigate = useNavigate();
  const [job, setJob] = useState<QuizJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<BuildResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  useEffect(() => {
    let live = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const j = await api.quizJob(jobId);
        if (!live) return;
        setJob(j); setError(null);
        if (j.done && j.result) {
          if (j.result.status === "ready" && j.result.quiz_id) { navigate(`/quiz/${j.result.quiz_id}`, { replace: true }); return; }
          setResult(j.result);
          return;
        }
        timer = setTimeout(poll, 1500);
      } catch (e) {
        if (!live) return;
        if (e instanceof ApiError && e.status === 404) { setError("This quiz is no longer being prepared. Start again from the Quiz page."); return; }
        setError(errorMessage(e));
      }
    };
    void poll();
    return () => { live = false; clearTimeout(timer); };
  }, [jobId, navigate, tick]);

  const again = useCallback(async (continueId: string | null) => {
    const b = lastBuild();
    if (!b) { navigate("/quiz"); return; }
    setBusy(true); setActionError(null);
    try {
      const body = { ...b, continue_quiz_id: continueId };
      const { job_id } = await api.buildQuiz(body);
      rememberBuild(b);
      setResult(null); setJob(null);
      navigate(`/quiz/build/${job_id}`, { replace: true });
    } catch (e) { setActionError(errorMessage(e)); } finally { setBusy(false); }
  }, [navigate]);

  async function startWith5(id: string) {
    setBusy(true); setActionError(null);
    try { await api.acceptQuiz(id); navigate(`/quiz/${id}`, { replace: true }); } catch (e) { setActionError(errorMessage(e)); setBusy(false); }
  }
  async function discard(id: string | null) {
    setBusy(true);
    try { if (id) await api.discardQuiz(id); navigate("/quiz"); } catch (e) { setActionError(errorMessage(e)); setBusy(false); }
  }

  const have = job?.have ?? 0;
  const requested = job?.requested ?? 0;
  const pct = requested ? Math.round((have / requested) * 100) : 0;

  return (
    <QuizFrame center>
      <PageTitle>{result ? (result.status === "offer" ? "Some questions are ready" : "Quiz not ready") : "Quiz"}</PageTitle>
      {error ? (
        <Notice tone="error" action={<div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setTick((t) => t + 1)}>Try again</Button><Button size="sm" variant="outline" onClick={() => navigate("/quiz")}>Back</Button></div>}>{error}</Notice>
      ) : result ? (
        <div className="space-y-4">
          <Notice>{result.message || (result.status === "offer" ? `${result.have} of ${result.requested} questions are ready.` : "The quiz could not be completed.")}</Notice>
          {actionError && <Notice tone="error">{actionError}</Notice>}
          <div className="flex flex-wrap gap-2">
            {result.status === "offer" && result.quiz_id && (
              <>
                <Button onClick={() => void startWith5(result.quiz_id!)} disabled={busy}>Start with 5</Button>
                <Button variant="outline" onClick={() => void again(result.quiz_id)} disabled={busy}>Continue preparing</Button>
                <Button variant="outline" onClick={() => void discard(result.quiz_id)} disabled={busy}>Discard</Button>
              </>
            )}
            {result.status !== "offer" && (
              <>
                {result.have > 0 && <Button onClick={() => void again(null)} disabled={busy}>Continue preparing</Button>}
                <Button variant="outline" onClick={() => navigate("/quiz")} disabled={busy}>Back to Quiz</Button>
              </>
            )}
          </div>
        </div>
      ) : (
        <div aria-live="polite">
          <ProgressRow phase="waiting" label="Preparing your quiz" />
          <p className="mt-4 text-[16px]">{job ? `${have} of ${requested} questions ready` : "Starting…"}</p>
          <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-line" role="progressbar" aria-valuemin={0} aria-valuemax={requested || 100} aria-valuenow={have} aria-label="Questions ready">
            <div className="h-full rounded-full bg-accent transition-[width] duration-500" style={{ width: `${pct}%` }} />
          </div>
          {job?.note && <p className="mt-3 text-[13px] text-muted">{job.note}</p>}
          <p className="mt-8 text-[13px] text-muted">This can take a minute. You can stay on this page.</p>
        </div>
      )}
    </QuizFrame>
  );
}
