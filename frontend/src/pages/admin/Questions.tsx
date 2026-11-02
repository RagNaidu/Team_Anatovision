import { useEffect, useState } from "react";
import { api, errorMessage } from "@/lib/api";
import type { QuestionRow } from "@/lib/types";
import { useIsDesktop } from "@/hooks/useMediaQuery";
import { Checkbox } from "@/components/ui/checkbox";
import { Notice, Skeleton } from "@/components/ui/misc";
import { Sheet } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { cn, formatDateTime } from "@/lib/utils";
import { AnswerMarkdown } from "@/pages/ask/AnswerMarkdown";
import { typeLabel } from "@/lib/citations";
import { AdminFrame, ErrorLine, Pager } from "./shared";

function Answer({ row }: { row: QuestionRow }) {
  const m = row.message;
  return (
    <div className="space-y-4">
      <div>
        <p className="serif-label">{row.student} · {formatDateTime(row.created_at)}</p>
        <h2 className="mt-1 font-serif text-[20px] font-semibold leading-snug">{row.question}</h2>
      </div>
      <p className="serif-label !text-[13px]">The answer exactly as the student saw it</p>
      {!m ? <Notice>The student deleted this chat, so the answer is no longer stored.</Notice> : (
        <div className="rounded-xl border border-line bg-surface p-4">
          {m.kind === "answer" || m.kind === "term_lookup"
            ? <AnswerMarkdown markdown={m.markdown} sources={m.sources} />
            : <p className="text-[15px]">{m.markdown}</p>}
          {m.sources.length > 0 && (
            <ul className="mt-4 space-y-2 border-t border-line pt-3">
              {m.sources.map((s) => (
                <li key={s.n} className="text-[13px]"><span className="font-semibold text-accent">{s.n}</span> {s.title} <span className="text-muted">· {s.subtitle || typeLabel(s.type)}</span></li>
              ))}
            </ul>
          )}
          {m.footer?.basis_line && <p className="mt-3 text-[13px] text-muted">{m.footer.basis_line}</p>}
          {m.footer?.access_note && <p className="text-[13px] text-muted">{m.footer.access_note}</p>}
        </div>
      )}
    </div>
  );
}

export default function Questions() {
  const isDesktop = useIsDesktop();
  const [web, setWeb] = useState(false);
  const [flagged, setFlagged] = useState(false);
  const [page, setPage] = useState(1);
  const [rows, setRows] = useState<QuestionRow[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [tries, setTries] = useState(0);

  useEffect(() => { setPage(1); }, [web, flagged]);
  useEffect(() => {
    let live = true;
    setError(null);
    api.adminQuestions({ web, flagged, page }).then((r) => { if (live) { setRows(r.items); setTotal(r.total); } }).catch((e) => live && setError(errorMessage(e)));
    return () => { live = false; };
  }, [web, flagged, page, tries]);
  const current = rows?.find((r) => r.id === sel) ?? null;

  return (
    <AdminFrame title="Questions" sub="What students asked. Preview questions are never listed." wide>
      <div className="mb-4 flex flex-wrap gap-6">
        <label className="flex cursor-pointer items-center gap-2.5 text-[14px]"><Checkbox checked={web} onCheckedChange={(c) => setWeb(c === true)} aria-label="Web-sourced only" /> Web-sourced only</label>
        <label className="flex cursor-pointer items-center gap-2.5 text-[14px]"><Checkbox checked={flagged} onCheckedChange={(c) => setFlagged(c === true)} aria-label="Flagged only" /> Flagged only</label>
      </div>
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)]">
        <div>
          {error ? <ErrorLine message={error} retry={() => setTries((t) => t + 1)} /> : !rows ? (
            <div className="space-y-2" aria-label="Loading">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-11 !rounded-lg" />)}</div>
          ) : rows.length === 0 ? <Notice>No questions match these filters.</Notice> : (
            <>
              <div className="overflow-x-auto rounded-xl border border-line bg-surface">
                <table className="w-full min-w-[520px] text-left text-[14px]">
                  <thead><tr className="border-b border-line text-[13px] text-muted">
                    <th className="px-4 py-2.5 font-normal">Student</th><th className="px-2 py-2.5 font-normal">Question</th><th className="px-2 py-2.5 font-normal">Type</th><th className="px-4 py-2.5 font-normal">When</th>
                  </tr></thead>
                  <tbody>
                    {rows.map((r) => (
                      <tr key={r.id} className={cn("cursor-pointer border-b border-line last:border-0 hover:bg-surface-2", sel === r.id && "bg-surface-2")} onClick={() => setSel(r.id)}>
                        <td className="whitespace-nowrap px-4 py-2.5">{r.student}</td>
                        <td className="max-w-[320px] px-2 py-2.5">
                          <button type="button" onClick={(e) => { e.stopPropagation(); setSel(r.id); }} aria-pressed={sel === r.id} className="line-clamp-2 w-full text-left">{r.question}</button>
                        </td>
                        <td className="whitespace-nowrap px-2 py-2.5 text-[12px]">
                          <span className="text-muted">{r.kind.replace("_", " ")}</span>
                          {r.web && <span className="ml-1.5 rounded-full bg-warn-soft px-2 py-0.5 text-warn">Web</span>}
                          {r.flagged && <span className="ml-1.5 rounded-full bg-accent-soft px-2 py-0.5 text-accent-soft-ink">Flagged</span>}
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
        </div>
        {isDesktop ? (
          <aside className="sticky top-0 self-start rounded-xl border border-line bg-surface p-5" aria-label="Answer">
            {current ? <Answer row={current} /> : <p className="text-[14px] text-muted">Choose a question to see the answer the student received.</p>}
          </aside>
        ) : (
          <Sheet open={Boolean(current)} onOpenChange={(o) => !o && setSel(null)} side="bottom" title="Answer" className="h-[86dvh] overflow-hidden rounded-t-2xl bg-surface">
            <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto p-5">{current && <Answer row={current} />}<Button className="mt-4" variant="outline" onClick={() => setSel(null)}>Close</Button></div>
          </Sheet>
        )}
      </div>
    </AdminFrame>
  );
}
