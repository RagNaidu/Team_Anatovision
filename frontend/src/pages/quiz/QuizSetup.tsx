import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Lock } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { QuizBuildBody, QuizHistoryItem, QuizLatest } from "@/lib/types";
import { useData } from "@/state/data";
import { Notice, PageTitle, Segmented, Skeleton } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { formatDate, cn } from "@/lib/utils";
import { QuizFrame, lastBuild, rememberBuild } from "./shared";

export default function QuizSetup() {
  const { scope, scopeError } = useData();
  const navigate = useNavigate();
  const location = useLocation();
  const [mode, setMode] = useState<"materials" | "topic">("materials");
  const [lectureIds, setLectureIds] = useState<string[]>([]);
  const [guideIds, setGuideIds] = useState<string[]>([]);
  const [topic, setTopic] = useState("");
  const [n, setN] = useState<5 | 10>(5);
  const [reviewedOnly, setReviewedOnly] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<QuizLatest | null | undefined>(undefined);
  const [history, setHistory] = useState<QuizHistoryItem[] | null>(null);
  const [histError, setHistError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const auto = useRef(false);

  useEffect(() => {
    let live = true;
    api.quizLatest().then((l) => live && setLatest(l)).catch((e) => { if (live) { setLatest(null); setNotice(errorMessage(e)); } });
    api.quizHistory().then((h) => live && setHistory(h)).catch((e) => live && setHistError(errorMessage(e)));
    return () => { live = false; };
  }, []);

  async function start(body: QuizBuildBody) {
    setBusy(true); setError(null);
    try {
      const { job_id } = await api.buildQuiz(body);
      rememberBuild(body);
      navigate(`/quiz/build/${job_id}`);
    } catch (e) { setError(errorMessage(e)); setBusy(false); }
  }

  // "Quiz me on this" from the source panel arrives with a ready request.
  useEffect(() => {
    const a = (location.state as { autoBuild?: { lecture_ids: string[]; n: 5 | 10 } } | null)?.autoBuild;
    if (a && !auto.current) {
      auto.current = true;
      window.history.replaceState({}, "");
      void start({ mode: "materials", lecture_ids: a.lecture_ids, guide_ids: [], n: a.n, reviewed_only: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state]);

  function submit() {
    if (mode === "topic") {
      const t = topic.trim();
      if (t.length < 3) { setError("A topic needs 3 to 80 characters."); return; }
      void start({ mode, topic: t, n, reviewed_only: reviewedOnly });
    } else {
      if (!lectureIds.length && !guideIds.length) { setError("Choose at least one lecture or guide."); return; }
      void start({ mode, lecture_ids: lectureIds, guide_ids: guideIds, n, reviewed_only: reviewedOnly });
    }
  }
  async function discard(id: string) {
    try { await api.discardQuiz(id); setLatest(null); } catch (e) { setNotice(errorMessage(e)); }
  }
  async function startWith5(id: string) {
    try { await api.acceptQuiz(id); navigate(`/quiz/${id}`); } catch (e) { setNotice(errorMessage(e)); }
  }
  async function continuePreparing(id: string) {
    const b = lastBuild();
    if (!b) { setNotice("Choose what to quiz yourself on below, then build again."); return; }
    await start({ ...b, continue_quiz_id: id });
  }

  const grantedLectures = scope?.lectures ?? [];
  const guides = scope?.guides ?? [];
  const toggle = (arr: string[], set: (a: string[]) => void, id: string, on: boolean) => set(on ? [...arr, id] : arr.filter((x) => x !== id));
  const allIds = { l: grantedLectures.filter((l) => l.granted).map((l) => l.id), g: guides.filter((g) => g.granted).map((g) => g.id) };

  return (
    <QuizFrame>
      <PageTitle sub="Practice questions written from your lectures and dissection guides.">Quiz</PageTitle>

      {notice && <Notice className="mb-4" tone="error">{notice}</Notice>}
      {latest === undefined ? <Skeleton className="mb-6 h-20 !rounded-xl" /> : latest && (
        <div className="mb-6 rounded-xl border border-line bg-surface p-4" role="region" aria-label="Unfinished quiz">
          {latest.status === "open" ? (
            <>
              <p className="text-[15px]">You have an unfinished quiz ({latest.answered} of {latest.length} answered)</p>
              <div className="mt-3 flex gap-2">
                <Button size="sm" onClick={() => navigate(`/quiz/${latest.id}`)}>Resume</Button>
                <Button size="sm" variant="outline" onClick={() => void discard(latest.id)}>Discard</Button>
              </div>
            </>
          ) : (
            <>
              <p className="text-[15px]">A quiz is waiting for you. Some questions are ready, and you can start with 5 or keep preparing.</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button size="sm" onClick={() => void startWith5(latest.id)}>Start with 5</Button>
                <Button size="sm" variant="outline" onClick={() => void continuePreparing(latest.id)}>Continue preparing</Button>
                <Button size="sm" variant="outline" onClick={() => void discard(latest.id)}>Discard</Button>
              </div>
            </>
          )}
        </div>
      )}

      <form onSubmit={(e) => { e.preventDefault(); submit(); }} className="space-y-6" aria-label="Build a quiz">
        <Segmented<"materials" | "topic"> label="Quiz source" value={mode} onChange={(v) => { setMode(v); setError(null); }}
          options={[{ value: "materials", label: "My lectures and guides" }, { value: "topic", label: "A topic" }]} />

        {mode === "materials" ? (
          scopeError ? <Notice tone="error">{scopeError}</Notice> : !scope ? <Skeleton className="h-40 !rounded-xl" /> : (
            <div className="space-y-5">
              <div className="flex items-center justify-between">
                <p className="serif-label !text-[15px]">Choose what to include</p>
                <button type="button" className="text-[13px] text-accent underline underline-offset-2"
                  onClick={() => { const all = lectureIds.length === allIds.l.length && guideIds.length === allIds.g.length; setLectureIds(all ? [] : allIds.l); setGuideIds(all ? [] : allIds.g); }}>
                  {lectureIds.length === allIds.l.length && guideIds.length === allIds.g.length && allIds.l.length + allIds.g.length > 0 ? "Clear all" : "Select all"}
                </button>
              </div>
              <fieldset>
                <legend className="mb-1.5 text-[14px] font-medium text-body-2">Lectures</legend>
                <ul className="grid gap-1 sm:grid-cols-2">
                  {grantedLectures.map((l) => (
                    <li key={l.id}>
                      <label className={cn("flex items-center gap-2.5 rounded-lg border border-line bg-surface px-3 py-2.5 text-[14px]", l.granted ? "cursor-pointer hover:bg-surface-2" : "cursor-not-allowed opacity-60")}>
                        <Checkbox disabled={!l.granted} checked={lectureIds.includes(l.id)} onCheckedChange={(c) => toggle(lectureIds, setLectureIds, l.id, c === true)} aria-label={l.title} />
                        <span className="min-w-0 flex-1">{l.title}</span>
                        {!l.granted && <span className="flex shrink-0 items-center gap-1 text-[12px] text-muted"><Lock size={12} strokeWidth={1.5} aria-hidden /> Ask your instructor</span>}
                      </label>
                    </li>
                  ))}
                </ul>
              </fieldset>
              <fieldset>
                <legend className="mb-1.5 text-[14px] font-medium text-body-2">Dissection guides</legend>
                <ul className="grid gap-1 sm:grid-cols-2">
                  {guides.map((g) => (
                    <li key={g.id}>
                      <label className={cn("flex items-center gap-2.5 rounded-lg border border-line bg-surface px-3 py-2.5 text-[14px]", g.granted ? "cursor-pointer hover:bg-surface-2" : "cursor-not-allowed opacity-60")}>
                        <Checkbox disabled={!g.granted} checked={guideIds.includes(g.id)} onCheckedChange={(c) => toggle(guideIds, setGuideIds, g.id, c === true)} aria-label={`Class ${g.class_number} ${g.title}`} />
                        <span className="min-w-0 flex-1"><span className="serif-label mr-1.5">Class {g.class_number}</span>{g.title}</span>
                        {!g.granted && <span className="flex shrink-0 items-center gap-1 text-[12px] text-muted"><Lock size={12} strokeWidth={1.5} aria-hidden /> Ask your instructor</span>}
                      </label>
                    </li>
                  ))}
                </ul>
              </fieldset>
            </div>
          )
        ) : (
          <div>
            <label htmlFor="topic" className="serif-label mb-1.5 block !text-[15px]">Topic</label>
            <input id="topic" value={topic} maxLength={80} onChange={(e) => setTopic(e.target.value)} placeholder="For example: rotator cuff muscles"
              className="h-11 w-full rounded-lg border border-line-strong bg-surface px-3 text-[15px]" />
            <p className="mt-1 text-right text-[12px] tabular-nums text-muted">{topic.length} / 80</p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-x-8 gap-y-4">
          <div>
            <p className="serif-label mb-1.5 !text-[15px]">Number of questions</p>
            <Segmented<5 | 10> label="Number of questions" value={n} onChange={setN} options={[{ value: 5, label: "5" }, { value: 10, label: "10" }]} />
          </div>
          <label className="flex cursor-pointer items-center gap-2.5 text-[14px]">
            <Checkbox checked={reviewedOnly} onCheckedChange={(c) => setReviewedOnly(c === true)} aria-label="Only questions approved by the instructor" />
            Only questions approved by the instructor
          </label>
        </div>

        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" size="lg" disabled={busy}>{busy ? "Starting…" : "Build quiz"}</Button>
      </form>

      <section className="mt-12" aria-label="Past quizzes">
        <h2 className="serif-label mb-2 !text-[15px]">Past quizzes</h2>
        {histError ? <p className="text-[14px] text-muted">{histError}</p> : !history ? <Skeleton className="h-10" /> : history.length === 0 ? (
          <p className="text-[14px] text-muted">Quizzes you finish will be listed here.</p>
        ) : (
          <ul className="divide-y divide-line border-y border-line">
            {history.map((h) => (
              <li key={h.id}>
                <Link to={`/quiz/${h.id}/results`} className="flex items-center justify-between px-1 py-3 text-[15px] hover:bg-surface-2">
                  <span>{formatDate(h.submitted)}</span><span className="text-body-2">{h.score} of {h.length}</span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </QuizFrame>
  );
}
