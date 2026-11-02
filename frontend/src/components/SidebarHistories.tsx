import { useEffect, useState } from "react";
import { useLocation, useMatch, useNavigate } from "react-router-dom";
import { ChevronDown, Globe } from "lucide-react";
import { useData } from "@/state/data";
import { HistoryList, type HistoryEntry } from "./HistoryList";
import { cn } from "@/lib/utils";

/** Quiz mode: past quizzes, "Femoral triangle · 3/5". */
export function QuizHistory() {
  const { quizHistory, quizHistoryError, refreshQuizHistory, removeQuiz } = useData();
  const navigate = useNavigate();
  const match = useMatch("/quiz/:id/results");
  const { pathname } = useLocation();
  useEffect(() => { void refreshQuizHistory(); }, [refreshQuizHistory, pathname]);
  const items: HistoryEntry[] | null = quizHistory && quizHistory.map((q) => ({
    id: q.id, to: `/quiz/${q.id}/results`, updated_at: q.submitted, plainLabel: `${q.title} · ${q.score}/${q.length}`,
    label: <span className="flex items-center gap-1.5"><span className="truncate">{q.title} · {q.score}/{q.length}</span>{q.web && <Globe size={12} strokeWidth={1.5} className="shrink-0 text-side-muted" aria-label="Built from the web" />}</span>,
  }));
  return (
    <div className="scroll-side min-h-0 flex-1 overflow-y-auto">
      <HistoryList heading="Past quizzes" items={items} error={quizHistoryError} retry={() => void refreshQuizHistory()}
        emptyText="Quizzes you finish will be listed here." confirmTitle="Delete this quiz?"
        confirmText={(e) => `“${e.plainLabel}” will be removed from your history. This can't be undone.`}
        isActive={(e) => match?.params.id === e.id}
        onDelete={async (e) => { await removeQuiz(e.id); if (match?.params.id === e.id) navigate("/quiz"); }} />
    </div>
  );
}

/** Guide mode: the guides worked on and the station reached. Collapsed inside a station (the station list is there instead). */
export function GuideHistory({ collapsible }: { collapsible: boolean }) {
  const { guideHistory, guideHistoryError, refreshGuideHistory, removeGuideHistory } = useData();
  const { pathname } = useLocation();
  const [open, setOpen] = useState(!collapsible);
  useEffect(() => { setOpen(!collapsible); }, [collapsible]);
  useEffect(() => { void refreshGuideHistory(); }, [refreshGuideHistory, pathname.split("/").slice(0, 4).join("/")]); // eslint-disable-line react-hooks/exhaustive-deps
  const items: HistoryEntry[] | null = guideHistory && guideHistory.map((g) => ({
    id: g.id, updated_at: g.updated_at, plainLabel: g.title, label: g.title, sub: g.notice ? "Updated: your place was reset" : `Station ${g.station + 1} of ${g.count}`,
    to: g.kind === "lecture" ? `/guide/lecture/${g.ref}/${g.station}` : `/guide/${g.ref}/${g.station}`,
  }));
  const here = (e: HistoryEntry) => pathname.startsWith(e.to.split("/").slice(0, e.to.includes("/lecture/") ? 4 : 3).join("/"));
  return (
    <div>
      {collapsible && (
        <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center justify-between px-5 py-2 font-serif text-[13px] italic text-side-faint hover:text-side-ink">
          History <ChevronDown size={14} strokeWidth={1.5} className={cn("transition-transform duration-200", open && "rotate-180")} aria-hidden />
        </button>
      )}
      {open && (
        <HistoryList heading={collapsible ? undefined : "History"} items={items} error={guideHistoryError} retry={() => void refreshGuideHistory()}
          emptyText="Guides you work on will be listed here, with the station you reached." confirmTitle="Delete from history?"
          confirmText={(e) => `“${e.plainLabel}” and the station you reached will be removed from your history. The guide itself stays available.`}
          isActive={here} onDelete={async (e) => { await removeGuideHistory(e.id); }} />
      )}
    </div>
  );
}
