import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Plus, X } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { BankData, BankDetail } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Notice, Select, Skeleton } from "@/components/ui/misc";
import { cn, formatDateTime } from "@/lib/utils";
import { AdminFrame, ErrorLine } from "./shared";
import { SOURCE_LABEL, StatusPill, UsePill } from "./bankUi";

const EMPTY: BankData = { stem: "", lead_in: "", options: [{ id: "A", text: "" }, { id: "B", text: "" }, { id: "C", text: "" }, { id: "D", text: "" }], answer: "A", explanation: "", lecture: "", guide: "", section: "", region: "", tags: [],
  difficulty: "", source: "instructor", status: "draft", use: "practice", objective: "" };
const FIELD_LABEL: Record<string, string> = { lead_in: "Question", stem: "Stem", options: "Options", answer: "Answer", explanation: "Explanation", lecture: "Lecture", guide: "Guide", section: "Section", region: "Region", tags: "Tags",
  difficulty: "Difficulty", status: "Status", use: "Use", source: "Source", objective: "Objective", links: "Links to the notes", created: "Created" };
const input = "w-full rounded-lg border border-line-strong bg-bone px-2.5 py-2 text-[15px] text-ink";
type Tab = "versions" | "comments" | "stats";

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return <label className="block"><span className="text-[14px] font-medium text-body-2">{label}</span>{hint && <span className="ml-2 text-[12px] text-muted">{hint}</span>}<div className="mt-1">{children}</div></label>;
}

export default function QuestionEditor() {
  const { qid = "" } = useParams();
  const nav = useNavigate();
  const isNew = qid === "new";
  const [doc, setDoc] = useState<BankDetail | null>(null);
  const [form, setForm] = useState<BankData>(EMPTY);
  const [tagsText, setTagsText] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<Tab>("versions");
  const [comment, setComment] = useState("");
  const [tries, setTries] = useState(0);

  const apply = useCallback((d: BankDetail) => { setDoc(d); setForm(d.data); setTagsText(d.data.tags.join(", ")); }, []);
  useEffect(() => {
    if (isNew) { setDoc(null); setForm(EMPTY); setTagsText(""); return; }
    let live = true;
    api.bankGet(qid).then((d) => live && (apply(d), setError(null))).catch((e) => live && setError(errorMessage(e)));
    return () => { live = false; };
  }, [qid, isNew, apply, tries]);

  const dirty = doc ? JSON.stringify({ ...form, tags: tagsText.split(",").map((t) => t.trim()).filter(Boolean) }) !== JSON.stringify(doc.data) : true;
  const filled = form.options.filter((o) => o.text.trim());
  const setOpt = (i: number, text: string) => setForm({ ...form, options: form.options.map((o, j) => (j === i ? { ...o, text } : o)) });

  async function run(fn: () => Promise<BankDetail>, ok?: string) {
    setBusy(true); setError(null); setMsg(null);
    try { const d = await fn(); apply(d); if (ok) setMsg(ok); return d; } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  async function save() {
    const data = { ...form, tags: tagsText.split(",").map((t) => t.trim()).filter(Boolean), options: form.options.filter((o) => o.text.trim()).map((o, i) => ({ id: "ABCDE"[i], text: o.text })) };
    const answerText = form.options.find((o) => o.id === form.answer)?.text.trim();
    data.answer = "ABCDE"[Math.max(0, data.options.findIndex((o) => o.text === answerText))];
    if (isNew) {
      setBusy(true); setError(null);
      try { const d = await api.bankCreate({ ...data, note }); nav(`/admin/bank/${encodeURIComponent(d.id)}`, { replace: true }); } catch (e) { setError(errorMessage(e)); setBusy(false); }
      return;
    }
    await run(() => api.bankSave(qid, { ...data, note }), "Saved as a new version. The rule checks were re-run.");
    setNote("");
  }

  if (error && !doc && !isNew) return <AdminFrame title="Question bank"><Link to="/admin/bank" className="mb-4 inline-flex items-center gap-1 text-[14px] text-accent"><ArrowLeft size={14} aria-hidden /> All questions</Link><ErrorLine message={error} retry={() => setTries((t) => t + 1)} /></AdminFrame>;
  if (!doc && !isNew) return <AdminFrame title="Question bank"><Skeleton className="h-8 w-1/2" /><Skeleton className="mt-4 h-64 !rounded-xl" /></AdminFrame>;
  const flags = doc?.flags.filter((f) => !f.dismissed) ?? [];

  return (
    <AdminFrame title={isNew ? "New question" : "Edit question"} wide sub={doc ? <span className="inline-flex flex-wrap items-center gap-2"><StatusPill status={doc.data.status} /><UsePill use={doc.data.use} /><span>{SOURCE_LABEL[doc.data.source]} · version {doc.version}{doc.sample ? " · sample (fake)" : ""}</span></span> : "Write the question, then save it as a draft."}>
      <Link to="/admin/bank" className="mb-4 inline-flex items-center gap-1 text-[14px] text-accent hover:underline"><ArrowLeft size={14} aria-hidden /> All questions</Link>
      {msg && <Notice className="mb-4" action={<Button size="sm" variant="ghost" onClick={() => setMsg(null)}>Dismiss</Button>}>{msg}</Notice>}
      {error && <ErrorLine message={error} />}
      {doc?.needs_recheck && (
        <Notice className="mb-4" action={<Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => api.bankRecheck(qid), "Marked as re-checked.")}>Mark as re-checked</Button>}>
          <strong className="font-semibold text-ink">Needs re-check.</strong> {doc.needs_recheck}. Nothing was changed: the question is as you left it.
        </Notice>
      )}
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); void save(); }} aria-label="Question">
          <Field label="Question (lead-in)" hint="the actual question, e.g. “Which nerve …?”"><textarea className={input} rows={2} value={form.lead_in} onChange={(e) => setForm({ ...form, lead_in: e.target.value })} required /></Field>
          <Field label="Stem" hint="optional context before the question"><textarea className={input} rows={2} value={form.stem} onChange={(e) => setForm({ ...form, stem: e.target.value })} /></Field>
          <fieldset>
            <legend className="text-[14px] font-medium text-body-2">Options <span className="text-[12px] font-normal text-muted">pick the correct one</span></legend>
            <ul className="mt-1 space-y-2">
              {form.options.map((o, i) => (
                <li key={i} className="flex items-center gap-2">
                  <input type="radio" name="answer" checked={form.answer === o.id} onChange={() => setForm({ ...form, answer: o.id })} aria-label={`Option ${o.id} is correct`} className="accent-[rgb(var(--accent))]" />
                  <span className="w-5 text-[14px] font-medium text-muted">{o.id}</span>
                  <input className={cn(input, "flex-1")} value={o.text} onChange={(e) => setOpt(i, e.target.value)} aria-label={`Option ${o.id}`} />
                  {form.options.length > 2 && <button type="button" aria-label={`Remove option ${o.id}`} className="rounded p-1 text-muted hover:bg-surface-2" onClick={() => { const rest = form.options.filter((_, j) => j !== i).map((x, j) => ({ ...x, id: "ABCDE"[j] })); setForm({ ...form, options: rest, answer: form.answer === o.id ? "A" : rest.find((x) => x.text === form.options.find((y) => y.id === form.answer)?.text)?.id ?? "A" }); }}><X size={15} /></button>}
                </li>
              ))}
            </ul>
            {form.options.length < 5 && <Button type="button" size="sm" variant="ghost" className="mt-2" onClick={() => setForm({ ...form, options: [...form.options, { id: "ABCDE"[form.options.length], text: "" }] })}><Plus size={14} aria-hidden /> Add an option</Button>}
          </fieldset>
          <Field label="Explanation" hint="shown to students after they submit"><textarea className={input} rows={3} value={form.explanation} onChange={(e) => setForm({ ...form, explanation: e.target.value })} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Lecture"><input className={input} value={form.lecture} onChange={(e) => setForm({ ...form, lecture: e.target.value })} /></Field>
            <Field label="Dissection guide"><input className={input} value={form.guide} onChange={(e) => setForm({ ...form, guide: e.target.value })} placeholder="Dissection Guide, Class 17" /></Field>
            <Field label="Section"><input className={input} value={form.section} onChange={(e) => setForm({ ...form, section: e.target.value })} /></Field>
            <Field label="Region"><input className={input} value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} /></Field>
            <Field label="Tags" hint="comma separated"><input className={input} value={tagsText} onChange={(e) => setTagsText(e.target.value)} /></Field>
            <Field label="Difficulty"><Select className="w-full" value={form.difficulty} onChange={(e) => setForm({ ...form, difficulty: e.target.value as BankData["difficulty"] })}><option value="">Not set</option><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></Select></Field>
            <Field label="Status"><Select className="w-full" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value as BankData["status"] })}><option value="draft">Draft</option><option value="approved">Approved</option><option value="retired">Retired</option></Select></Field>
            <Field label="Use" hint="exam-secure is never shown to students"><Select className="w-full" value={form.use} onChange={(e) => setForm({ ...form, use: e.target.value as BankData["use"] })}><option value="practice">Practice</option><option value="exam_secure">Exam-secure</option></Select></Field>
          </div>
          <Field label="What changed?" hint="optional, kept in the version history"><input className={input} value={note} onChange={(e) => setNote(e.target.value)} maxLength={200} /></Field>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" disabled={busy || !dirty || !form.lead_in.trim() || filled.length < 2}>{busy ? "Saving…" : isNew ? "Create question" : "Save as new version"}</Button>
            {!isNew && <Button type="button" variant="outline" disabled={busy || dirty} onClick={() => run(() => api.bankCheck(qid), "AI checks finished. They only flag: nothing was changed.")}>Run AI checks</Button>}
            {!isNew && dirty && <span className="text-[13px] text-muted">Save first to run the AI checks.</span>}
          </div>
        </form>

        <aside className="space-y-4" aria-label="Checks and history">
          {!isNew && (
            <section className="rounded-xl border border-line bg-surface p-4" aria-label="AI flags">
              <h2 className="font-serif text-[18px] font-semibold">{flags.length ? `${flags.length} flag${flags.length === 1 ? "" : "s"}` : "No flags"}</h2>
              <p className="mt-0.5 text-[12px] text-muted">The AI only flags. Nothing here changes the question or its status.</p>
              <ul className="mt-2 space-y-2">
                {flags.map((f) => (
                  <li key={f.kind + f.code} className="rounded-lg bg-surface-2 p-2.5 text-[13px]">
                    <span className={cn("mr-1.5 rounded-full px-2 py-0.5 text-[11px] font-medium", f.severity === "warn" ? "bg-warn-soft text-warn" : "bg-sunken text-body-2")}>{{ nbme: "Item writing", key: "Answer key", duplicate: "Duplicate", tag: "Link", stats: "Statistics" }[f.kind] ?? f.kind}</span>
                    {f.message}
                    {f.kind !== "stats" && <button type="button" className="ml-2 text-[12px] text-accent underline" onClick={() => run(() => api.bankDismiss(qid, f.kind, f.code, true))}>Dismiss</button>}
                  </li>
                ))}
              </ul>
            </section>
          )}
          {!isNew && doc && (
            <section className="rounded-xl border border-line bg-surface p-4">
              <div role="tablist" aria-label="History" className="mb-3 flex gap-1 border-b border-line">
                {([["versions", "Versions"], ["comments", `Comments${doc.comments.length ? ` (${doc.comments.length})` : ""}`], ["stats", "Statistics"]] as [Tab, string][]).map(([t, l]) => (
                  <button key={t} role="tab" aria-selected={tab === t} type="button" onClick={() => setTab(t)} className={cn("-mb-px border-b-2 px-2.5 py-1.5 text-[13px]", tab === t ? "border-accent font-medium text-ink" : "border-transparent text-muted hover:text-ink")}>{l}</button>
                ))}
              </div>
              {tab === "versions" && (
                <ol className="space-y-2" aria-label="Versions">
                  {doc.versions.map((v) => (
                    <li key={v.version} className="rounded-lg border border-line p-2.5 text-[13px]">
                      <div className="flex items-center justify-between gap-2"><span className="font-medium">Version {v.version}{v.version === doc.version ? " (current)" : ""}</span>
                        {v.version !== doc.version && <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => api.bankRestore(qid, v.version), `Restored version ${v.version} as a new version.`)}>Restore</Button>}</div>
                      <p className="text-muted">{formatDateTime(v.at)} · {v.by}{v.note ? ` · ${v.note}` : ""}</p>
                      <p className="mt-0.5 text-body-2">Changed: {v.changed.map((c) => FIELD_LABEL[c] ?? c).join(", ")}</p>
                    </li>
                  ))}
                </ol>
              )}
              {tab === "comments" && (
                <div>
                  <ul className="space-y-2" aria-label="Comments">
                    {doc.comments.length === 0 && <li className="text-[13px] text-muted">No comments yet. Comments are internal: students never see them.</li>}
                    {doc.comments.map((c) => <li key={c.id} className="rounded-lg bg-surface-2 p-2.5 text-[13px]"><span className="text-muted">{c.by} · {formatDateTime(c.at)}</span><p className="whitespace-pre-wrap">{c.text}</p></li>)}
                  </ul>
                  <textarea className={cn(input, "mt-3")} rows={2} value={comment} onChange={(e) => setComment(e.target.value)} aria-label="New comment" placeholder="Add an internal comment" />
                  <Button size="sm" className="mt-2" disabled={busy || !comment.trim()} onClick={async () => { await run(() => api.bankComment(qid, comment)); setComment(""); }}>Add comment</Button>
                </div>
              )}
              {tab === "stats" && (
                <div className="text-[13px]">
                  {doc.stats.n === 0 ? <p className="text-muted">Not used in a student quiz yet.</p> : (
                    <>
                      <dl className="grid grid-cols-3 gap-2">
                        <div><dt className="text-muted">Times used</dt><dd className="font-serif text-[22px] font-semibold">{doc.stats.n}</dd></div>
                        <div><dt className="text-muted">Correct</dt><dd className="font-serif text-[22px] font-semibold">{doc.stats.p_correct === null ? "–" : `${Math.round(doc.stats.p_correct * 100)}%`}</dd></div>
                        <div><dt className="text-muted">Discrimination</dt><dd className="font-serif text-[22px] font-semibold">{doc.stats.discrimination === null ? "–" : doc.stats.discrimination.toFixed(2)}</dd></div>
                      </dl>
                      <p className="mt-2 text-muted">Based on {doc.stats.n} attempt{doc.stats.n === 1 ? "" : "s"}. {doc.stats.enough ? `Flags need at least ${doc.stats.min_for_flags}.` : `Below ${doc.stats.min_for_stats} attempts these numbers are only a hint.`} Nothing is ever retired automatically.</p>
                      <table className="mt-3 w-full text-left"><thead><tr className="text-muted"><th className="py-1 font-medium">Option</th><th className="py-1 text-right font-medium">Picked</th></tr></thead>
                        <tbody>{doc.stats.distractors.map((d) => <tr key={d.text} className="border-t border-line"><td className="py-1">{d.text}{d.correct ? " (correct)" : ""}</td><td className="py-1 text-right">{d.picks}</td></tr>)}</tbody></table>
                    </>
                  )}
                </div>
              )}
            </section>
          )}
        </aside>
      </div>
    </AdminFrame>
  );
}
