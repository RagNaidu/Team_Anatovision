import { useEffect, useState } from "react";
import { ExternalLink } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { WebQuizItem } from "@/lib/types";
import { Notice, Skeleton } from "@/components/ui/misc";
import { formatDateTime } from "@/lib/utils";
import { AdminFrame, ErrorLine, Pager } from "./shared";

export default function WebQuizzes() {
  const [rows, setRows] = useState<WebQuizItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    let live = true;
    setError(null);
    api.adminWebQuizzes(page).then((r) => { if (live) { setRows(r.items); setTotal(r.total); } }).catch((e) => live && setError(errorMessage(e)));
    return () => { live = false; };
  }, [page, tries]);

  return (
    <AdminFrame title="Web quizzes" sub="Quizzes with questions built from Wikipedia because the course material did not cover the topic. Preview quizzes are never listed." wide>
      {error ? <ErrorLine message={error} retry={() => setTries((t) => t + 1)} /> : !rows ? (
        <div className="space-y-2" aria-label="Loading">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-14 !rounded-xl" />)}</div>
      ) : rows.length === 0 ? <Notice>No student has taken a web-built quiz yet.</Notice> : (
        <>
          <div className="overflow-x-auto rounded-xl border border-line bg-surface">
            <table className="w-full min-w-[640px] text-left text-[14px]">
              <thead><tr className="border-b border-line text-[13px] text-muted">
                <th className="px-4 py-2.5 font-normal">Student</th><th className="px-2 py-2.5 font-normal">Topic</th><th className="px-2 py-2.5 font-normal">Web questions</th>
                <th className="px-2 py-2.5 font-normal">Score</th><th className="px-2 py-2.5 font-normal">Source</th><th className="px-4 py-2.5 font-normal">When</th>
              </tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id} className="border-b border-line align-top last:border-0">
                    <td className="whitespace-nowrap px-4 py-2.5">{r.student}</td>
                    <td className="px-2 py-2.5">{r.title}</td>
                    <td className="whitespace-nowrap px-2 py-2.5">{r.web_questions} of {r.length}</td>
                    <td className="whitespace-nowrap px-2 py-2.5">{r.status === "submitted" && r.score !== null ? `${r.score} of ${r.length}` : <span className="text-muted">In progress</span>}</td>
                    <td className="px-2 py-2.5 text-[13px]">
                      {r.sources.map((s) => (
                        <p key={s.url ?? s.title}>{s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-accent underline underline-offset-2">{s.title} <ExternalLink size={11} strokeWidth={1.75} aria-hidden /></a> : s.title}
                          {s.license && <span className="text-muted"> · {s.license}</span>}</p>
                      ))}
                    </td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-muted">{formatDateTime(r.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pager page={page} total={total} onPage={setPage} />
        </>
      )}
    </AdminFrame>
  );
}
