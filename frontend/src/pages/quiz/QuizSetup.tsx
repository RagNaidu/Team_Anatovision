import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, errorMessage } from "@/lib/api";
import type { QuizBuildBody, QuizLatest } from "@/lib/types";
import { useData } from "@/state/data";
import { Notice, PageTitle, Segmented, Skeleton } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { compareLectures } from "@/lib/utils";
import { MultiSelect } from "@/components/MultiSelect";
import { QuizFrame, lastBuild, rememberBuild } from "./shared";
import { TopicInput } from "./TopicInput";

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
  const [differentStyle, setDifferentStyle] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latest, setLatest] = useState<QuizLatest | null | undefined>(undefined);
  const [notice, setNotice] = useState<string | null>(null);
  const auto = useRef(false);

  useEffect(() => {
    let live = true;
    api.quizLatest().then((l) => live && setLatest(l)).catch((e) => { if (live) { setLatest(null); setNotice(errorMessage(e)); } });
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
      void start({ mode, topic: t, n, reviewed_only: reviewedOnly, different_style: differentStyle });
    } else {
      if (!lectureIds.length && !guideIds.length) { setError("Choose at least one lecture or guide."); return; }
      void start({ mode, lecture_ids: lectureIds, guide_ids: guideIds, n, reviewed_only: reviewedOnly, different_style: differentStyle });
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

  const lectureOptions = useMemo(() => [...(scope?.lectures ?? [])].sort((a, b) => compareLectures(a.title, b.title)).map((l) => ({ id: l.id, label: l.title, locked: !l.granted })), [scope]);
  const guideOptions = useMemo(() => [...(scope?.guides ?? [])].sort((a, b) => a.class_number - b.class_number || a.title.localeCompare(b.title))
    .map((g) => ({ id: g.id, label: `Class ${g.class_number} · ${g.title}`, locked: !g.granted })), [scope]);

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
          scopeError ? <Notice tone="error">{scopeError}</Notice> : !scope ? <Skeleton className="h-28 !rounded-xl" /> : (
            <div className="grid gap-4 sm:grid-cols-2">
              <MultiSelect label="Lectures" noun="lecture" nounPlural="lectures" options={lectureOptions} value={lectureIds} onChange={setLectureIds} />
              <MultiSelect label="Dissection guides" noun="guide" nounPlural="guides" options={guideOptions} value={guideIds} onChange={setGuideIds} />
            </div>
          )
        ) : (
          <div>
            <TopicInput value={topic} onChange={setTopic} />
            <div className="mt-1 flex items-start justify-between gap-4 text-[12px] text-muted">
              <span>If your course material doesn't cover the topic, questions are built from Wikipedia and are marked "Not from course notes".</span>
              <span className="shrink-0 tabular-nums">{topic.length} / 80</span>
            </div>
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
          <label className="flex cursor-pointer items-center gap-2.5 text-[14px]">
            <Checkbox checked={differentStyle} onCheckedChange={(c) => setDifferentStyle(c === true)} aria-label="A different style from the instructor's examples" disabled={reviewedOnly} />
            A different style from the instructor's examples
          </label>
        </div>
        {mode === "topic" && reviewedOnly && (
          <Notice>Questions built from the web are switched off while this is checked. Only instructor-approved questions from the course material are used.</Notice>
        )}

        {error && <Notice tone="error">{error}</Notice>}
        <Button type="submit" size="lg" disabled={busy}>{busy ? "Starting…" : "Build quiz"}</Button>
      </form>

    </QuizFrame>
  );
}
