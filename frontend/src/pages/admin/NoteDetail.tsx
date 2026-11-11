import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Check, Loader2 } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { NoteAudit, NoteDetail, NoteDiff, NoteVersion, Student } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Notice, Select, Skeleton } from "@/components/ui/misc";
import { cn, formatDate, formatDateTime } from "@/lib/utils";
import { AdminFrame, ErrorLine } from "./shared";
import { DIFF_LABEL, DIFF_TONE, StatusChip } from "./noteUi";
import GuideAnnotations from "./GuideAnnotations";

type Tab = "preview" | "annotations" | "versions" | "activity";

function DiffRows({ diff }: { diff: NoteDiff }) {
  const c = diff.counts;
  return (
    <div>
      <p className="text-[14px] text-body-2">Against {diff.against ?? "the previous version"}: {["unchanged", "edited", "rewritten", "added", "removed"].filter((k) => c[k]).map((k) => `${c[k]} ${DIFF_LABEL[k].toLowerCase()}`).join(", ") || "no differences"}.</p>
      <ul className="mt-2 space-y-2">
        {diff.rows.map((r, i) => (
          <li key={i} className="rounded-lg border border-line bg-surface p-3 text-[14px]">
            <div className="flex items-center gap-2"><span className={cn("rounded-full px-2 py-0.5 text-[12px] font-medium", DIFF_TONE[r.status])}>{DIFF_LABEL[r.status]}</span><span className="text-muted">{r.path}</span></div>
            {r.old && <p className="mt-2 whitespace-pre-wrap rounded bg-accent-soft/60 px-2 py-1 text-body-2 line-through decoration-accent/50">{r.old}</p>}
            {r.new && <p className="mt-1 whitespace-pre-wrap rounded bg-ok-soft/70 px-2 py-1">{r.new}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Steps({ job }: { job: NonNullable<NoteDetail["job"]> }) {
  return (
    <ol className="space-y-2" aria-label="Progress">
      {job.steps.map((s, i) => {
        const done = i < job.step_index, current = i === job.step_index;
        return (
          <li key={s} className={cn("flex items-center gap-3 text-[15px]", done ? "text-body-2" : current ? "font-medium text-ink" : "text-muted")} aria-current={current ? "step" : undefined}>
            <span className={cn("flex h-5 w-5 items-center justify-center rounded-full border", done ? "border-ok bg-ok text-white" : current ? "border-accent text-accent" : "border-line-strong")} aria-hidden>
              {done ? <Check size={12} strokeWidth={3} /> : current ? <Loader2 size={12} className="animate-spin" /> : null}
            </span>{s}
          </li>
        );
      })}
    </ol>
  );
}

function PublishDialog({ doc, open, onOpenChange, onDone }: { doc: NoteDetail; open: boolean; onOpenChange: (o: boolean) => void; onDone: (m: string) => void }) {
  const first = doc.live_version === null;
  const [access, setAccess] = useState<"all" | "selected" | "none" | "same">(doc.replaces ? "same" : "none");
  const [students, setStudents] = useState<Student[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (open && first) api.adminStudents().then(setStudents).catch(() => setStudents([])); if (!open) setError(null); }, [open, first]);
  async function go() {
    setBusy(true); setError(null);
    try {
      const r = await api.notesPublish(doc.id, access, picked);
      onOpenChange(false);
      onDone(`Published version ${r.version}.${first ? ` ${r.granted} student${r.granted === 1 ? " can" : "s can"} open it.` : ""}${r.flags_added ? ` ${r.flags_added} AI flag${r.flags_added === 1 ? "" : "s"} added to the review queue.` : ""}`);
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  const opts: [typeof access, string][] = [["all", "All students"], ["selected", "Selected students"], ["none", "No one yet"], ...(doc.replaces ? [["same", `Same students as ${doc.replaces_title ?? "the document it replaces"}`] as [typeof access, string]] : [])];
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={`Publish ${doc.title}`} description={first ? "Students can ask about it as soon as it is published. Choose who can open it." : "The new version replaces the live one. Who can open it does not change."}>
        {first && (
          <fieldset>
            <legend className="sr-only">Who can open it</legend>
            {opts.map(([v, label]) => (
              <label key={v} className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-[14px] hover:bg-surface-2">
                <input type="radio" name="access" checked={access === v} onChange={() => setAccess(v)} className="accent-[rgb(var(--accent))]" /> {label}
              </label>
            ))}
            {access === "selected" && (
              <ul className="mt-2 max-h-40 overflow-y-auto rounded-lg border border-line p-1">
                {students.map((s) => (
                  <li key={s.id}><label className="flex cursor-pointer items-center gap-2.5 rounded px-2 py-1 text-[14px] hover:bg-surface-2">
                    <Checkbox checked={picked.includes(s.id)} onCheckedChange={(c) => setPicked(c === true ? [...picked, s.id] : picked.filter((x) => x !== s.id))} aria-label={s.name} /> {s.name}
                  </label></li>
                ))}
              </ul>
            )}
          </fieldset>
        )}
        <p className="mt-3 text-[13px] text-muted">Publishing builds a staged copy, checks that the new text can be found, keeps a backup of what is live, then switches over. It can be undone.</p>
        {error && <p role="alert" className="mt-3 text-[14px] text-accent">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={busy || (access === "selected" && picked.length === 0)} onClick={go}>{busy ? "Publishing…" : "Publish"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function ConfirmDialog({ open, onOpenChange, title, description, action, label, typed, danger, onRun }: {
  open: boolean; onOpenChange: (o: boolean) => void; title: string; description: string; action?: string; label: string; typed?: string; danger?: boolean; onRun: () => Promise<void>;
}) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!open) { setText(""); setError(null); setBusy(false); } }, [open]);
  async function go() { setBusy(true); setError(null); try { await onRun(); onOpenChange(false); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); } }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title={title} description={description}>
        {typed && (
          <>
            <label htmlFor="typed-title" className="block text-[14px] text-body-2">Type <strong className="font-semibold text-ink">{typed}</strong> to confirm</label>
            <input id="typed-title" value={text} onChange={(e) => setText(e.target.value)} autoComplete="off" className="mt-1 h-9 w-full rounded-md border border-line-strong bg-surface px-2.5 text-[14px]" />
          </>
        )}
        {error && <p role="alert" className="mt-3 text-[14px] text-accent">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant={danger ? "danger" : "primary"} disabled={busy || (typed !== undefined && text.trim() !== typed)} onClick={go}>{busy ? "Working…" : action ?? label}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function Editor({ doc, onSaved }: { doc: NoteDetail; onSaved: (m: string) => void }) {
  const [editing, setEditing] = useState<number | null>(null);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function save(i: number) {
    setBusy(true); setError(null);
    try { const r = await api.notesEdit(doc.id, [{ index: i, text }], ""); setEditing(null); onSaved(`Saved as version ${r.version} and published.${r.fixes_to_recheck ? ` ${r.fixes_to_recheck} verified decision${r.fixes_to_recheck === 1 ? "" : "s"} need a second look.` : ""}`); }
    catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }
  return (
    <ul className="space-y-3" aria-label="Sections">
      {doc.sections.map((s, i) => (
        <li key={i} className="rounded-xl border border-line bg-surface p-4">
          <div className="flex items-start justify-between gap-3">
            <p className="text-[13px] font-medium text-muted">{s.path.join(" › ")}</p>
            {doc.editable && editing !== i && <Button size="sm" variant="outline" onClick={() => { setEditing(i); setText(s.text); setError(null); }} aria-label={`Edit ${s.path.join(" › ")}`}>Edit</Button>}
          </div>
          {editing === i ? (
            <div className="mt-2">
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={Math.min(14, Math.max(4, text.split("\n").length + 1))} aria-label="Section text"
                className="w-full resize-y rounded-lg border border-line-strong bg-bone p-2.5 font-serif text-[15px] leading-relaxed" />
              <p className="mt-1 text-[12px] text-muted">Saving creates a new version and publishes it. The earlier version stays in Versions.</p>
              {error && <p role="alert" className="mt-1 text-[14px] text-accent">{error}</p>}
              <div className="mt-2 flex justify-end gap-2"><Button size="sm" variant="ghost" onClick={() => setEditing(null)}>Cancel</Button><Button size="sm" disabled={busy || !text.trim()} onClick={() => save(i)}>{busy ? "Saving…" : "Save new version"}</Button></div>
            </div>
          ) : <p className="mt-1 whitespace-pre-wrap font-serif text-[15px] leading-relaxed">{s.text}</p>}
        </li>
      ))}
    </ul>
  );
}

export default function NoteDetailPage() {
  const { docId = "" } = useParams();
  const nav = useNavigate();
  const [doc, setDoc] = useState<NoteDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("preview");
  const [msg, setMsg] = useState<string | null>(null);
  const [dlg, setDlg] = useState<"" | "publish" | "discard" | "archive" | "restore" | "purge">("");
  const [versions, setVersions] = useState<NoteVersion[] | null>(null);
  const [audit, setAudit] = useState<NoteAudit[] | null>(null);
  const [vdiff, setVdiff] = useState<{ v: number; diff: NoteDiff } | null>(null);
  const [rollTo, setRollTo] = useState<number | null>(null);
  const fileIn = useRef<HTMLInputElement>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);

  const load = useCallback(() => api.notesDetail(docId).then((d) => { setDoc(d); setError(null); return d; }).catch((e) => setError(errorMessage(e))), [docId]);
  useEffect(() => { setDoc(null); load(); }, [load, tries]);
  useEffect(() => {
    if (doc?.job?.status !== "processing") return;
    const t = setInterval(load, 1500);
    return () => clearInterval(t);
  }, [doc?.job?.status, load]);
  useEffect(() => {
    if (tab === "versions") api.notesVersions(docId).then(setVersions).catch((e) => setError(errorMessage(e)));
    if (tab === "activity") api.notesAudit(docId).then(setAudit).catch((e) => setError(errorMessage(e)));
  }, [tab, docId, doc?.updated_at]);

  const refresh = (m: string) => { setMsg(m); setVersions(null); setAudit(null); setVdiff(null); return load(); };
  async function pickFile(f?: File) {
    if (!f) return;
    setFileError(null);
    try { await api.notesReplace(docId, f); await refresh("The new file is being prepared. Check the preview, then publish it."); } catch (e) { setFileError(errorMessage(e)); }
  }
  async function showDiff(v: number) { try { setVdiff({ v, diff: await api.notesVersionDiff(docId, v) }); } catch (e) { setError(errorMessage(e)); } }

  if (error && !doc) return <AdminFrame title="Notes"><Link to="/admin/notes" className="mb-4 inline-flex items-center gap-1 text-[14px] text-accent"><ArrowLeft size={14} aria-hidden /> All documents</Link><ErrorLine message={error} retry={() => setTries((t) => t + 1)} /></AdminFrame>;
  if (!doc) return <AdminFrame title="Notes"><Skeleton className="h-8 w-1/2" /><Skeleton className="mt-4 h-40 !rounded-xl" /></AdminFrame>;

  const job = doc.job;
  const processing = job?.status === "processing";
  const failed = job?.status === "failed";
  const waiting = doc.status !== "published" && doc.status !== "archived" || doc.has_pending;
  const readyToPublish = job?.status === "ready" && (doc.status === "ready" || doc.has_pending);

  return (
    <AdminFrame title={doc.title} wide sub={<span className="inline-flex flex-wrap items-center gap-2"><StatusChip status={doc.status} /> <span>{doc.kind === "guide" ? "Dissection guide" : "Lecture notes"} · {doc.region || "No region"} · version {doc.version}</span></span>}>
      <Link to="/admin/notes" className="mb-4 inline-flex items-center gap-1 text-[14px] text-accent hover:underline"><ArrowLeft size={14} aria-hidden /> All documents</Link>
      {msg && <Notice className="mb-4" action={<Button size="sm" variant="ghost" onClick={() => setMsg(null)}>Dismiss</Button>}>{msg}</Notice>}
      {error && <ErrorLine message={error} />}
      {fileError && <ErrorLine message={fileError} />}

      <div className="mb-5 flex flex-wrap items-center gap-2">
        {readyToPublish && <Button onClick={() => setDlg("publish")}>Publish</Button>}
        {(waiting && doc.status !== "archived") && <Button variant="outline" onClick={() => setDlg("discard")}>{doc.has_pending ? "Discard new version" : "Discard"}</Button>}
        {doc.status === "published" && !doc.has_pending && (
          <>
            <input ref={fileIn} type="file" accept=".docx,.doc,.pptx,.pdf" className="sr-only" aria-label="Choose a replacement file" onChange={(e) => { pickFile(e.target.files?.[0]); e.target.value = ""; }} />
            <Button variant="outline" onClick={() => fileIn.current?.click()}>Replace file</Button>
          </>
        )}
        {doc.status === "published" && <Button variant="danger" onClick={() => setDlg("archive")}>Archive</Button>}
        {doc.status === "archived" && <><Button onClick={() => setDlg("restore")}>Restore</Button><Button variant="danger" onClick={() => setDlg("purge")}>Purge…</Button></>}
      </div>

      {doc.status === "archived" && <Notice className="mb-5">Archived{doc.archived_at ? ` on ${formatDate(doc.archived_at, { month: "short", day: "numeric", year: "numeric" })}` : ""}. It is not used in any answer. {doc.purge_after ? `It can be restored until ${formatDate(doc.purge_after, { month: "short", day: "numeric", year: "numeric" })}.` : ""}</Notice>}

      {processing && job && (
        <section className="rounded-xl border border-line bg-surface p-5" aria-live="polite" aria-label="Preparing the document">
          <h2 className="mb-3 font-serif text-[20px] font-semibold">Preparing the document</h2>
          <Steps job={job} />
        </section>
      )}
      {failed && job && <Notice tone="error" className="mb-4">{job.error || "This file could not be processed."} Discard it and upload another copy.</Notice>}

      {!processing && !failed && (
        <>
          <div role="tablist" aria-label="Document" className="mb-4 flex gap-1 border-b border-line">
            {([["preview", "Content"], ...(doc.guide_id ? [["annotations", "Image marks"]] : []), ["versions", "Versions"], ["activity", "Activity"]] as [Tab, string][]).map(([t, l]) => (
              <button key={t} role="tab" aria-selected={tab === t} type="button" onClick={() => setTab(t)}
                className={cn("-mb-px border-b-2 px-3 py-2 text-[14px]", tab === t ? "border-accent font-medium text-ink" : "border-transparent text-muted hover:text-ink")}>{l}</button>
            ))}
          </div>

          {tab === "preview" && (
            <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
              <div>
                {doc.has_pending && <Notice className="mb-4">A new version ({job?.version}) is waiting. What you see below is that waiting version, not what students see.</Notice>}
                {doc.diff && (
                  <details className="mb-4 rounded-xl border border-line bg-surface p-4" open>
                    <summary className="cursor-pointer text-[15px] font-medium">What changed against {doc.diff.against}</summary>
                    <div className="mt-3"><DiffRows diff={doc.diff} /></div>
                  </details>
                )}
                {doc.sections.length === 0 ? <Notice>No sections to show.</Notice> : <Editor doc={doc} onSaved={refresh} />}
              </div>
              <aside className="space-y-4 lg:sticky lg:top-0 lg:self-start" aria-label="Mapping and checks">
                {(waiting || doc.status === "published") && (
                  <section className="rounded-xl border border-line bg-surface p-4">
                    <h2 className="font-serif text-[18px] font-semibold">Where it belongs</h2>
                    <p className="mt-0.5 text-[12px] text-muted">Worked out from the content. Change it if it is wrong.</p>
                    <label className="mt-3 block text-[13px] font-medium text-body-2" htmlFor="region">Region</label>
                    <Select id="region" className="mt-1 w-full" value={doc.region} onChange={(e) => api.notesMapping(doc.id, { region: e.target.value }).then(() => refresh("Region changed.")).catch((er) => setError(errorMessage(er)))}>
                      {[...new Set([doc.region, ...doc.regions, "Other"].filter(Boolean))].map((r) => <option key={r}>{r}</option>)}
                    </Select>
                    {doc.kind === "guide" && (
                      <>
                        <label className="mt-3 block text-[13px] font-medium text-body-2" htmlFor="lecture">Matching lecture</label>
                        <Select id="lecture" className="mt-1 w-full" value={doc.mapping.lecture} disabled={doc.status === "published"}
                          onChange={(e) => api.notesMapping(doc.id, { lecture: e.target.value }).then(() => refresh("Lecture changed.")).catch((er) => setError(errorMessage(er)))}>
                          <option value="">None (instructors only)</option>{doc.lectures.map((l) => <option key={l}>{l}</option>)}
                        </Select>
                      </>
                    )}
                    {doc.status !== "published" && !doc.has_pending && doc.live_version === null && (
                      <>
                        <label className="mt-3 block text-[13px] font-medium text-body-2" htmlFor="replaces">Replaces</label>
                        <Select id="replaces" className="mt-1 w-full" value={doc.replaces ?? ""} onChange={(e) => api.notesMapping(doc.id, { replaces: e.target.value }).then(() => refresh("Saved.")).catch((er) => setError(errorMessage(er)))}>
                          <option value="">Nothing (a new document)</option>
                          {doc.overlap && <option value={doc.overlap.doc_id}>{doc.overlap.title}</option>}
                        </Select>
                      </>
                    )}
                  </section>
                )}
                {doc.overlap && !doc.replaces && (
                  <Notice>
                    <strong className="font-semibold text-ink">This looks like {doc.overlap.title}</strong> ({Math.round(doc.overlap.score * 100)}% similar text, {doc.overlap.shared_sections} of {doc.overlap.sections} sections shared).
                    {doc.overlap.suggest_replace ? " Publishing it as a separate document would give two versions of the same lecture." : ""}
                    {doc.overlap.suggest_replace && <div className="mt-2"><Button size="sm" variant="outline" className="h-auto whitespace-normal py-1.5 text-left" onClick={() => api.notesMapping(doc.id, { replaces: doc.overlap!.doc_id }).then(() => refresh(`It will replace ${doc.overlap!.title} when you publish.`))}>Replace {doc.overlap.title}</Button></div>}
                  </Notice>
                )}
                {doc.replaces && doc.live_version === null && <Notice>When published this archives <strong className="font-semibold text-ink">{doc.replaces_title ?? doc.replaces}</strong>. You can restore that for 30 days.</Notice>}
                {doc.flags.count > 0 && (
                  <section className="rounded-xl border border-line bg-surface p-4" aria-label="AI flags">
                    <h2 className="font-serif text-[18px] font-semibold">{doc.flags.count} AI flag{doc.flags.count === 1 ? "" : "s"}</h2>
                    <p className="mt-0.5 text-[12px] text-muted">Only new or changed sections were checked. They go to the review queue when you publish. Nothing is rewritten.</p>
                    <ul className="mt-2 space-y-2">
                      {doc.flags.items.slice(0, 6).map((f, i) => (
                        <li key={i} className="rounded-lg bg-surface-2 p-2.5 text-[13px]"><span className="font-medium">“{f.quote}”</span><span className="mt-0.5 block text-muted">{f.issue}</span></li>
                      ))}
                    </ul>
                  </section>
                )}
              </aside>
            </div>
          )}

          {tab === "annotations" && doc.guide_id && <GuideAnnotations guideId={doc.guide_id} />}

          {tab === "versions" && (
            !versions ? <Skeleton className="h-24 !rounded-xl" /> : (
              <ul className="space-y-3" aria-label="Versions">
                {versions.map((v) => (
                  <li key={v.version} className="rounded-xl border border-line bg-surface p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="text-[15px] font-medium">Version {v.version} <span className="ml-1 rounded-full bg-surface-2 px-2 py-0.5 text-[12px] font-normal text-body-2">{v.status === "live" ? "Live" : v.status}</span></p>
                        <p className="text-[13px] text-muted">{formatDateTime(v.created_at)}{v.created_by ? ` · ${v.created_by}` : ""}{v.note ? ` · ${v.note}` : ""}</p>
                        {v.diff && <p className="mt-1 text-[13px] text-body-2">{Object.entries(v.diff).filter(([k, n]) => k !== "unchanged" && n).map(([k, n]) => `${n} ${k}`).join(", ") || "No changes"} against the version before</p>}
                      </div>
                      <div className="flex gap-2">
                        {v.diff && <Button size="sm" variant="outline" onClick={() => (vdiff?.v === v.version ? setVdiff(null) : showDiff(v.version))}>{vdiff?.v === v.version ? "Hide changes" : "Show changes"}</Button>}
                        {v.status === "superseded" && doc.status === "published" && <Button size="sm" variant="outline" onClick={() => setRollTo(v.version)}>Roll back to this</Button>}
                      </div>
                    </div>
                    {vdiff?.v === v.version && <div className="mt-3 border-t border-line pt-3"><DiffRows diff={vdiff.diff} /></div>}
                  </li>
                ))}
              </ul>
            )
          )}

          {tab === "activity" && (
            !audit ? <Skeleton className="h-24 !rounded-xl" /> : audit.length === 0 ? <Notice>Nothing has happened to this document in the manager yet.</Notice> : (
              <ol className="divide-y divide-line rounded-xl border border-line bg-surface" aria-label="Activity">
                {audit.map((a, i) => (
                  <li key={i} className="px-4 py-3 text-[14px]"><span className="font-medium capitalize">{a.action}</span> <span className="text-muted">by {a.user} · {formatDateTime(a.at)}</span>{a.detail && <p className="text-[13px] text-body-2">{a.detail}</p>}</li>
                ))}
              </ol>
            )
          )}
        </>
      )}

      <PublishDialog doc={doc} open={dlg === "publish"} onOpenChange={(o) => setDlg(o ? "publish" : "")} onDone={(m) => { setTab("preview"); refresh(m); }} />
      <ConfirmDialog open={dlg === "discard"} onOpenChange={(o) => setDlg(o ? "discard" : "")} title="Discard this?" description="The prepared text is deleted. What is live does not change." label="Discard" danger
        onRun={async () => { await api.notesDiscard(doc.id); if (doc.live_version === null) nav("/admin/notes"); else await refresh("Discarded."); }} />
      <ConfirmDialog open={dlg === "archive"} onOpenChange={(o) => setDlg(o ? "archive" : "")} title={`Archive ${doc.title}?`}
        description="It is taken out of every answer straight away. You can restore it for 30 days." label="Archive" danger onRun={async () => { const r = await api.notesArchive(doc.id); await refresh(`Archived. You can restore it until ${formatDate(r.restorable_until ?? new Date().toISOString(), { month: "short", day: "numeric" })}.`); }} />
      <ConfirmDialog open={dlg === "restore"} onOpenChange={(o) => setDlg(o ? "restore" : "")} title={`Restore ${doc.title}?`} description="It becomes available in answers again for the students who had it." label="Restore" onRun={async () => { await api.notesRestore(doc.id); await refresh("Restored."); }} />
      <ConfirmDialog open={dlg === "purge"} onOpenChange={(o) => setDlg(o ? "purge" : "")} title="Delete permanently?" typed={doc.title} label="Purge" action="Delete forever" danger
        description="Every version and the uploaded file are deleted and cannot be brought back. The activity log stays." onRun={async () => { await api.notesPurge(doc.id, doc.title); nav("/admin/notes"); }} />
      <ConfirmDialog open={rollTo !== null} onOpenChange={(o) => !o && setRollTo(null)} title={`Roll back to version ${rollTo}?`} description="Its text becomes a new version and goes live. Nothing is deleted: you can roll forward again." label="Roll back"
        onRun={async () => { await api.notesRollback(doc.id, rollTo!); setRollTo(null); await refresh(`Rolled back to version ${rollTo}.`); }} />
    </AdminFrame>
  );
}
