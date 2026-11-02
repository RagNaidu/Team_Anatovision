import { useCallback, useEffect, useState } from "react";
import { api, ApiError, errorMessage } from "@/lib/api";
import type { ReviewItem, ReviewStatus, ReviewType } from "@/lib/types";
import { useData } from "@/state/data";
import { useIsDesktop } from "@/hooks/useMediaQuery";
import { Button } from "@/components/ui/button";
import { Notice, Select, Skeleton } from "@/components/ui/misc";
import { Sheet } from "@/components/ui/sheet";
import { cn, shortLecture } from "@/lib/utils";
import { typeLabel } from "@/lib/citations";
import { AdminFrame, ErrorLine, Pager } from "./shared";

const TYPE_LABEL: Record<ReviewType, string> = {
  start_here: "Start here", confirmed_factual: "Confirmed factual", doubtful: "Doubtful", wording: "Wording", typo: "Typo", student_report: "Student report",
};

function Detail({ item, onDecided, onClose }: { item: ReviewItem; onDecided: () => void; onClose?: () => void }) {
  const [fix, setFix] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const report = item.type === "student_report";
  const decided = item.status !== "open" || done;
  useEffect(() => { setFix(""); setError(null); setDone(null); }, [item.id]);

  async function decide(action: "verify" | "dismiss") {
    setBusy(true); setError(null);
    try {
      await api.adminDecide(item.id, action, action === "verify" ? fix.trim() : undefined);
      setDone(action === "verify" ? "Verified. Students now see your correction in place of the line." : report ? "Marked as handled." : "Dismissed. The notes stay as written.");
      onDecided();
    } catch (e) {
      setError(errorMessage(e));
      if (e instanceof ApiError && e.status === 409) onDecided();
    } finally { setBusy(false); }
  }

  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center justify-between gap-2">
          <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-[12px] font-medium text-accent-soft-ink">{TYPE_LABEL[item.type] ?? item.type}</span>
          {onClose && <Button size="sm" variant="ghost" onClick={onClose}>Close</Button>}
        </div>
        <h2 className="mt-3 font-serif text-[20px] font-semibold leading-snug">{item.lecture}</h2>
        {item.section && <p className="text-[14px] text-muted">{item.section}</p>}
      </div>
      <section>
        <h3 className="serif-label mb-1 !font-sans !not-italic !text-[13px]">{report ? "The answer the student saw" : "Original text"}</h3>
        <blockquote className="whitespace-pre-wrap rounded-lg bg-surface-2 px-4 py-3 font-serif text-[15px] leading-relaxed">{item.original_text}</blockquote>
      </section>
      <section>
        <h3 className="serif-label mb-1 !font-sans !not-italic !text-[13px]">{report ? "Report" : "The AI's note"}</h3>
        <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-body-2">{item.ai_note}</p>
      </section>
      {item.sources.length > 0 && (
        <section>
          <h3 className="serif-label mb-1 !font-sans !not-italic !text-[13px]">Sources</h3>
          <ul className="space-y-2">
            {item.sources.map((s) => (
              <li key={s.n} className="rounded-lg border border-line px-3 py-2 text-[13px]">
                <p className="font-medium">{s.n}. {s.title} <span className="font-normal text-muted">· {typeLabel(s.type)}</span></p>
                {s.subtitle && <p className="text-muted">{s.subtitle}</p>}
                <p className="mt-1 font-serif text-[14px] text-body-2">{s.snippet}</p>
                {s.url && <a href={s.url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-block text-accent underline underline-offset-2">Open</a>}
              </li>
            ))}
          </ul>
        </section>
      )}
      {decided ? (
        <Notice>{done ?? (item.status === "verified" ? "Already verified." : "Already dismissed.")}</Notice>
      ) : (
        <section className="space-y-3 border-t border-line pt-4">
          <p className="text-[13px] text-muted">The AI only flags. You decide.</p>
          {!report && (
            <div>
              <label htmlFor="fix-text" className="mb-1 block text-[14px] text-body-2">Fix text</label>
              <textarea id="fix-text" rows={3} value={fix} onChange={(e) => setFix(e.target.value)} placeholder="The corrected wording students should see"
                className="w-full resize-y rounded-lg border border-line-strong bg-bone p-2.5 text-[14px]" />
            </div>
          )}
          {error && <p role="alert" className="text-[13px] text-accent">{error}</p>}
          <div className="flex flex-wrap gap-2">
            {!report && <Button onClick={() => void decide("verify")} disabled={busy || !fix.trim()}>Verify fix</Button>}
            <Button variant="outline" onClick={() => void decide("dismiss")} disabled={busy}>{report ? "Dismiss" : "Dismiss (notes are correct)"}</Button>
          </div>
        </section>
      )}
    </div>
  );
}

export default function ReviewQueue() {
  const { scope } = useData();
  const isDesktop = useIsDesktop();
  const [type, setType] = useState("");
  const [status, setStatus] = useState<ReviewStatus | "">("open");
  const [lecture, setLecture] = useState("");
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<ReviewItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [snap, setSnap] = useState<ReviewItem | null>(null); // keeps a just-decided item on screen after the list reloads without it
  const [tries, setTries] = useState(0);

  const load = useCallback(() => setTries((t) => t + 1), []);
  useEffect(() => { setPage(1); }, [type, status, lecture]);
  useEffect(() => {
    let live = true;
    setError(null);
    api.adminReview({ type, status, lecture, page }).then((r) => { if (live) { setItems(r.items); setTotal(r.total); } }).catch((e) => live && setError(errorMessage(e)));
    return () => { live = false; };
  }, [type, status, lecture, page, tries]);

  const current = items?.find((i) => i.id === sel) ?? (snap && snap.id === sel ? snap : null);
  const detail = current && <Detail item={current} onDecided={load} onClose={isDesktop ? undefined : () => setSel(null)} />;

  return (
    <AdminFrame title="Review queue" sub="The AI only flags. You decide." wide>
      <div className="mb-4 flex flex-wrap gap-3">
        <label className="flex items-center gap-2 text-[14px] text-body-2">Type
          <Select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="">All</option>{(Object.keys(TYPE_LABEL) as ReviewType[]).map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
          </Select></label>
        <label className="flex items-center gap-2 text-[14px] text-body-2">Status
          <Select value={status} onChange={(e) => setStatus(e.target.value as ReviewStatus | "")}>
            <option value="">All</option><option value="open">Open</option><option value="decided">Decided</option><option value="verified">Verified</option><option value="dismissed">Dismissed</option>
          </Select></label>
        <label className="flex items-center gap-2 text-[14px] text-body-2">Lecture
          <Select value={lecture} onChange={(e) => setLecture(e.target.value)} className="max-w-[220px]">
            <option value="">All</option>{scope?.lectures.map((l) => <option key={l.id} value={l.id}>{shortLecture(l.title)}</option>)}
          </Select></label>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,440px)]">
        <div>
          {error ? <ErrorLine message={error} retry={load} /> : !items ? (
            <div className="space-y-2" aria-label="Loading">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-[72px] !rounded-xl" />)}</div>
          ) : items.length === 0 ? <Notice>Nothing matches these filters.</Notice> : (
            <>
              <p className="mb-2 text-[13px] text-muted">{total} item{total === 1 ? "" : "s"}</p>
              <ul className="space-y-2">
                {items.map((i) => (
                  <li key={i.id}>
                    <button type="button" onClick={() => { setSel(i.id); setSnap(i); }} aria-pressed={sel === i.id}
                      className={cn("w-full rounded-xl border px-4 py-3 text-left transition-colors duration-150 hover:bg-surface-2", sel === i.id ? "border-accent bg-surface-2" : "border-line bg-surface")}>
                      <span className="flex items-center gap-2 text-[12px]">
                        <span className="rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent-soft-ink">{TYPE_LABEL[i.type]}</span>
                        <span className="text-muted">{shortLecture(i.lecture)}</span>
                        {i.status !== "open" && <span className="ml-auto text-muted">{i.status === "verified" ? "Verified" : "Dismissed"}</span>}
                      </span>
                      <span className="mt-1.5 line-clamp-2 block text-[14px] leading-snug">{i.original_text}</span>
                    </button>
                  </li>
                ))}
              </ul>
              <Pager page={page} total={total} onPage={setPage} />
            </>
          )}
        </div>
        {isDesktop ? (
          <aside className="sticky top-0 self-start rounded-xl border border-line bg-surface p-5" aria-label="Item detail">
            {detail ?? <p className="text-[14px] text-muted">Choose an item to see its details.</p>}
          </aside>
        ) : (
          <Sheet open={Boolean(current)} onOpenChange={(o) => !o && setSel(null)} side="bottom" title="Item detail" className="h-[86dvh] overflow-hidden rounded-t-2xl bg-surface">
            <div className="scroll-quiet min-h-0 flex-1 overflow-y-auto p-5">{detail}</div>
          </Sheet>
        )}
      </div>
    </AdminFrame>
  );
}
