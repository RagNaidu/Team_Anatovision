import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Download, FileUp, Plus, Search } from "lucide-react";
import { api, errorMessage, USE_MOCK } from "@/lib/api";
import type { BankFilters, BankImportPreview, BankImportResult, BankList } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Notice, Select, Skeleton } from "@/components/ui/misc";
import { cn } from "@/lib/utils";
import { AdminFrame, ErrorLine, Pager } from "./shared";
import { SOURCE_LABEL, StatusPill, UsePill } from "./bankUi";

function ImportDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (o: boolean) => void; onDone: (r: BankImportResult) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [pv, setPv] = useState<BankImportPreview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [status, setStatus] = useState("draft");
  const [use, setUse] = useState("exam_secure");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!open) { setPv(null); setMapping({}); setStatus("draft"); setUse("exam_secure"); setError(null); setBusy(false); } }, [open]);

  async function upload(f?: File) {
    if (!f) return;
    setBusy(true); setError(null);
    try { const p = await api.bankImportPreview(f); setPv(p); setMapping(p.mapping); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function remap(field: string, header: string) {
    if (!pv) return;
    const m = { ...mapping }; if (header) m[field] = header; else delete m[field];
    setMapping(m); setBusy(true); setError(null);
    try { const p = await api.bankImportPreview(null, pv.import_id, m); setPv(p); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function commit() {
    if (!pv) return;
    setBusy(true); setError(null);
    try { const r = await api.bankImportCommit(pv.import_id, mapping, status, use); onOpenChange(false); onDone(r); } catch (e) { setError(errorMessage(e)); setBusy(false); }
  }
  const templateHref = (kind: "csv" | "xlsx") => (USE_MOCK ? `data:text/csv;charset=utf-8,${encodeURIComponent("Question (lead-in),Stem / vignette,Option A,Option B,Option C,Option D,Option E,Correct answer,Explanation,Lecture,Dissection guide,Section,Region,Tags,Difficulty\n")}` : api.bankTemplateUrl(kind));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Import questions" description="CSV, Excel or Word. Any column layout: match your columns to the fields, check the preview, then import." className="max-h-[90dvh] max-w-3xl overflow-y-auto">
        <input ref={input} type="file" accept=".csv,.xlsx,.docx" className="sr-only" aria-label="Choose a file to import" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
        {!pv ? (
          <div>
            <button type="button" onClick={() => input.current?.click()} disabled={busy} className="flex w-full flex-col items-center gap-1 rounded-xl border border-dashed border-line-strong bg-surface-2 px-4 py-8 text-[14px] text-body-2 hover:bg-sunken">
              <FileUp size={20} strokeWidth={1.5} aria-hidden />{busy ? "Reading the file…" : "Choose a .csv, .xlsx or .docx file"}
            </button>
            <p className="mt-3 text-[13px] text-muted">No file yet? Download the template: <a className="text-accent underline" href={templateHref("csv")} download="question-template.csv">CSV</a> · <a className="text-accent underline" href={templateHref("xlsx")} download="question-template.xlsx">Excel</a>.
              A Word file should have numbered questions, A. B. C. options and “Answer: C”.</p>
          </div>
        ) : (
          <div className="space-y-5">
            <p className="text-[14px] text-body-2"><strong className="text-ink">{pv.filename}</strong>: {pv.n_rows} row{pv.n_rows === 1 ? "" : "s"}, {pv.ready} ready to import{pv.duplicates ? `, ${pv.duplicates} look like questions already in the bank` : ""}.</p>
            <section aria-label="Match your columns">
              <h3 className="font-serif text-[17px] font-semibold">Match your columns</h3>
              <div className="mt-2 grid gap-x-4 gap-y-2 sm:grid-cols-2">
                {pv.fields.map((f) => (
                  <label key={f.field} className="flex items-center justify-between gap-2 text-[14px]">
                    <span className={cn(["lead_in", "option_a", "option_b", "answer"].includes(f.field) && "font-medium")}>{f.label}{["lead_in", "option_a", "option_b", "answer"].includes(f.field) ? " *" : ""}</span>
                    <Select aria-label={`Column for ${f.label}`} value={mapping[f.field] ?? ""} onChange={(e) => remap(f.field, e.target.value)} className="w-[170px]" disabled={busy}>
                      <option value="">Not in my file</option>{pv.headers.map((h) => <option key={h} value={h}>{h}</option>)}
                    </Select>
                  </label>
                ))}
              </div>
            </section>
            <section aria-label="Preview">
              <h3 className="font-serif text-[17px] font-semibold">What will be created</h3>
              {pv.questions.length === 0 ? <Notice className="mt-2">No row can be imported yet. Map the question, at least two options and the correct answer.</Notice> : (
                <ul className="mt-2 divide-y divide-line rounded-lg border border-line text-[13px]">
                  {pv.questions.map((q) => (
                    <li key={q.row} className="px-3 py-2"><span className="text-muted">Row {q.row}</span> <span className="font-medium">{q.lead_in}</span><span className="block text-muted">{q.options} · answer {q.answer}</span>
                      {q.duplicate && <span className="block text-warn">Looks like {q.duplicate}: it will be flagged.</span>}</li>
                  ))}
                </ul>
              )}
              {pv.problems.length > 0 && <p className="mt-2 text-[13px] text-warn">{pv.problems.length} row{pv.problems.length === 1 ? "" : "s"} will be skipped: {pv.problems.slice(0, 3).map((p) => `row ${p.row} (${p.problem})`).join("; ")}{pv.problems.length > 3 ? "…" : ""}</p>}
            </section>
            <section className="grid gap-3 sm:grid-cols-2" aria-label="Import as">
              <label className="text-[14px]">Status
                <Select value={status} onChange={(e) => setStatus(e.target.value)} className="mt-1 w-full"><option value="draft">Draft</option><option value="approved">Approved</option></Select></label>
              <label className="text-[14px]">Use
                <Select value={use} onChange={(e) => setUse(e.target.value)} className="mt-1 w-full"><option value="exam_secure">Exam-secure (never shown to students)</option><option value="practice">Practice</option></Select></label>
            </section>
          </div>
        )}
        {error && <p role="alert" className="mt-3 text-[14px] text-accent">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          {pv && <Button disabled={busy || pv.ready === 0} onClick={commit}>{busy ? "Working…" : `Import ${pv.ready} question${pv.ready === 1 ? "" : "s"}`}</Button>}
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function QuestionBank() {
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const f: BankFilters = useMemo(() => ({ q: params.get("q") ?? "", status: params.get("status") ?? "", use: params.get("use") ?? "", source: params.get("source") ?? "", region: params.get("region") ?? "",
    lecture: params.get("lecture") ?? "", tag: params.get("tag") ?? "", difficulty: params.get("difficulty") ?? "", flagged: params.get("flagged") === "true", page: Number(params.get("page") ?? 1) || 1 }), [params]);
  const [data, setData] = useState<BankList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<string[]>([]);
  const [msg, setMsg] = useState<string | null>(null);
  const [tag, setTag] = useState("");
  const [open, setOpen] = useState(false);
  const [tries, setTries] = useState(0);
  const facets = useRef<Pick<BankList, "lectures" | "regions" | "tags">>({ lectures: [], regions: [], tags: [] });
  const set = (k: string, v: string) => { const p = new URLSearchParams(params); if (v) p.set(k, v); else p.delete(k); if (k !== "page") p.delete("page"); setParams(p, { replace: true }); };

  const load = useCallback(() => api.bankList(f).then((d) => { facets.current = { lectures: d.lectures, regions: d.regions, tags: d.tags }; setData(d); setError(null); }).catch((e) => setError(errorMessage(e))), [f]);
  useEffect(() => { const t = setTimeout(load, f.q ? 250 : 0); return () => clearTimeout(t); }, [load, tries, f.q]);

  async function bulk(action: string, value = "", label = "") {
    try { const r = await api.bankBulk(sel, action, value); setMsg(`${label || action}: ${r.changed} question${r.changed === 1 ? "" : "s"} changed.`); setSel([]); await load(); } catch (e) { setError(errorMessage(e)); }
  }
  const exportHref = USE_MOCK ? `data:text/csv;charset=utf-8,${encodeURIComponent("id,lead_in,status,use\n" + (data?.items ?? []).map((r) => [r.id, `"${r.lead_in}"`, r.status, r.use].join(",")).join("\n"))}` : api.bankExportUrl(f);
  const c = data?.counts;
  const allOn = !!data?.items.length && data.items.every((r) => sel.includes(r.id));

  return (
    <AdminFrame title="Question bank" sub="Your questions, plus the AI questions students' quizzes produce. Only approved practice questions ever reach students." wide>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <Search size={15} strokeWidth={1.5} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
          <input value={f.q} onChange={(e) => set("q", e.target.value)} placeholder="Search questions" aria-label="Search questions" className="h-9 w-full rounded-md border border-line-strong bg-surface pl-9 pr-3 text-[14px] text-ink placeholder:text-muted" />
        </div>
        <div className="ml-auto flex gap-2">
          <Button variant="outline" onClick={() => setOpen(true)}><FileUp size={15} strokeWidth={1.5} aria-hidden /> Import</Button>
          <a href={exportHref} download="question-bank.csv" className="inline-flex h-10 items-center gap-2 rounded-full border border-line-strong bg-surface px-4 text-[14px] font-medium hover:bg-surface-2"><Download size={15} strokeWidth={1.5} aria-hidden /> Export CSV</a>
          <Button onClick={() => nav("/admin/bank/new")}><Plus size={15} strokeWidth={1.5} aria-hidden /> New question</Button>
        </div>
      </div>
      <div className="mb-4 flex flex-wrap items-center gap-2" aria-label="Filters" role="group">
        <Select aria-label="Status" value={f.status} onChange={(e) => set("status", e.target.value)}><option value="">Any status</option><option value="draft">Draft</option><option value="approved">Approved</option><option value="retired">Retired</option></Select>
        <Select aria-label="Use" value={f.use} onChange={(e) => set("use", e.target.value)}><option value="">Any use</option><option value="practice">Practice</option><option value="exam_secure">Exam-secure</option></Select>
        <Select aria-label="Source" value={f.source} onChange={(e) => set("source", e.target.value)}><option value="">Any source</option>{Object.entries(SOURCE_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
        <Select aria-label="Lecture or guide" value={f.lecture} onChange={(e) => set("lecture", e.target.value)} className="max-w-[200px]"><option value="">Any lecture or guide</option>{facets.current.lectures.map((l) => <option key={l}>{l}</option>)}</Select>
        <Select aria-label="Region" value={f.region} onChange={(e) => set("region", e.target.value)}><option value="">Any region</option>{facets.current.regions.map((l) => <option key={l}>{l}</option>)}</Select>
        <Select aria-label="Tag" value={f.tag} onChange={(e) => set("tag", e.target.value)}><option value="">Any tag</option>{facets.current.tags.map((l) => <option key={l}>{l}</option>)}</Select>
        <Select aria-label="Difficulty" value={f.difficulty} onChange={(e) => set("difficulty", e.target.value)}><option value="">Any difficulty</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></Select>
        <label className="flex cursor-pointer items-center gap-2 text-[14px]"><Checkbox checked={f.flagged} onCheckedChange={(v) => set("flagged", v === true ? "true" : "")} aria-label="Flagged only" /> Flagged</label>
      </div>
      {c && <p className="mb-3 text-[13px] text-muted">{c.total} in the bank · {c.draft} draft · {c.approved} approved · {c.retired} retired · {c.exam_secure} exam-secure · {c.flagged} flagged{c.needs_recheck ? ` · ${c.needs_recheck} need a re-check` : ""}</p>}
      {msg && <Notice className="mb-3" action={<Button size="sm" variant="ghost" onClick={() => setMsg(null)}>Dismiss</Button>}>{msg}</Notice>}
      {sel.length > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-line-strong bg-surface-2 px-3 py-2" role="toolbar" aria-label="Bulk actions">
          <span className="mr-1 text-[14px] font-medium">{sel.length} selected</span>
          <Button size="sm" onClick={() => bulk("approve", "", "Approved")}>Approve</Button>
          <Button size="sm" variant="outline" onClick={() => bulk("retire", "", "Retired")}>Retire</Button>
          <Button size="sm" variant="outline" onClick={() => bulk("draft", "", "Set to draft")}>Draft</Button>
          <Button size="sm" variant="outline" onClick={() => bulk("set_use", "practice", "Use = practice")}>Practice</Button>
          <Button size="sm" variant="outline" onClick={() => bulk("set_use", "exam_secure", "Use = exam-secure")}>Exam-secure</Button>
          <Button size="sm" variant="outline" onClick={() => bulk("run_checks", "", "AI checks run")}>Run AI checks</Button>
          <input value={tag} onChange={(e) => setTag(e.target.value)} placeholder="Tag" aria-label="Tag to add or remove" className="h-8 w-28 rounded-md border border-line-strong bg-surface px-2 text-[13px]" />
          <Button size="sm" variant="outline" disabled={!tag.trim()} onClick={() => bulk("add_tag", tag.trim(), "Tag added")}>Add tag</Button>
          <Button size="sm" variant="ghost" onClick={() => setSel([])}>Clear</Button>
        </div>
      )}
      {error ? <ErrorLine message={error} retry={() => setTries((t) => t + 1)} /> : !data ? (
        <div className="space-y-2">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-16 !rounded-xl" />)}</div>
      ) : data.items.length === 0 ? <Notice>No questions match. Clear a filter, import a file or write a new question.</Notice> : (
        <>
          <div className="mb-1 flex items-center gap-2 px-4 text-[13px] text-muted"><Checkbox checked={allOn} onCheckedChange={(v) => setSel(v === true ? data.items.map((r) => r.id) : [])} aria-label="Select all on this page" /> Select all on this page</div>
          <ul className="overflow-hidden rounded-xl border border-line bg-surface" aria-label="Questions">
            {data.items.map((r) => (
              <li key={r.id} className="flex items-start gap-3 border-b border-line px-4 py-3 last:border-b-0 hover:bg-surface-2">
                <Checkbox className="mt-1" checked={sel.includes(r.id)} onCheckedChange={(v) => setSel(v === true ? [...sel, r.id] : sel.filter((x) => x !== r.id))} aria-label={`Select ${r.lead_in}`} />
                <Link to={`/admin/bank/${encodeURIComponent(r.id)}`} className="min-w-0 flex-1">
                  <span className="block text-[15px] font-medium text-ink">{r.lead_in}</span>
                  <span className="mt-1.5 flex flex-wrap items-center gap-1.5">
                    <StatusPill status={r.status} /><UsePill use={r.use} />
                    <span className="rounded-full bg-surface-2 px-2.5 py-0.5 text-[12px] text-body-2">{SOURCE_LABEL[r.source]}</span>
                    {r.sample && <span className="rounded-full border border-line-strong px-2.5 py-0.5 text-[12px] text-muted">Sample</span>}
                    {r.n_flags > 0 && <span className="rounded-full bg-warn-soft px-2.5 py-0.5 text-[12px] font-medium text-warn">{r.n_flags} flag{r.n_flags === 1 ? "" : "s"}</span>}
                    {r.needs_recheck && <span className="rounded-full bg-accent-soft px-2.5 py-0.5 text-[12px] font-medium text-accent-soft-ink">Needs re-check</span>}
                    <span className="text-[12px] text-muted">{[r.lecture, r.region, r.difficulty].filter(Boolean).join(" · ")}{r.used ? ` · used ${r.used}×` : ""}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          <Pager page={f.page ?? 1} total={data.total} per={50} onPage={(p) => set("page", String(p))} />
        </>
      )}
      <ImportDialog open={open} onOpenChange={setOpen} onDone={(r) => { setMsg(`Imported ${r.created} question${r.created === 1 ? "" : "s"}${r.skipped_duplicates ? `, skipped ${r.skipped_duplicates} duplicate${r.skipped_duplicates === 1 ? "" : "s"}` : ""}${r.problems.length ? `, ${r.problems.length} row${r.problems.length === 1 ? "" : "s"} could not be read` : ""}. Imported questions are drafts and exam-secure until you change them.`); void load(); }} />
    </AdminFrame>
  );
}
