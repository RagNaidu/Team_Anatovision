import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Search, Upload } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { NoteList } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Notice, Select, Skeleton } from "@/components/ui/misc";
import { formatDate } from "@/lib/utils";
import { AdminFrame, ErrorLine } from "./shared";
import { StatusChip } from "./noteUi";

const ACCEPT = ".docx,.doc,.pptx,.pdf";

function UploadDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const nav = useNavigate();
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [kind, setKind] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!open) { setFile(null); setKind(""); setError(null); setBusy(false); } }, [open]);
  async function go() {
    if (!file) return;
    setBusy(true); setError(null);
    try { const r = await api.notesUpload(file, kind || undefined); onOpenChange(false); nav(`/admin/notes/${encodeURIComponent(r.doc_id)}`); }
    catch (e) { setError(errorMessage(e)); setBusy(false); }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Upload notes or a guide" description="Word, PowerPoint or PDF. Nothing goes live until you publish it.">
        <input ref={input} type="file" accept={ACCEPT} className="sr-only" aria-label="Choose a file" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setError(null); }} />
        <button type="button" onClick={() => input.current?.click()} onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => { e.preventDefault(); setFile(e.dataTransfer.files?.[0] ?? null); }}
          className="flex w-full flex-col items-center gap-1 rounded-xl border border-dashed border-line-strong bg-surface-2 px-4 py-8 text-[14px] text-body-2 hover:bg-sunken">
          <Upload size={20} strokeWidth={1.5} aria-hidden />
          {file ? <span className="font-medium text-ink">{file.name}</span> : <span>Choose a file or drop it here</span>}
          <span className="text-[12px] text-muted">.docx, .doc, .pptx or .pdf</span>
        </button>
        <label className="mt-4 block text-[14px] font-medium text-body-2" htmlFor="note-kind">What is it?</label>
        <Select id="note-kind" value={kind} onChange={(e) => setKind(e.target.value)} className="mt-1 w-full">
          <option value="">Work it out from the file</option>
          <option value="note">Lecture notes</option>
          <option value="guide">Dissection guide (.pptx)</option>
        </Select>
        {error && <p role="alert" className="mt-3 text-[14px] text-accent">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button disabled={!file || busy} onClick={go}>{busy ? "Uploading…" : "Upload and prepare"}</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export default function Notes() {
  const [data, setData] = useState<NoteList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("");
  const [region, setRegion] = useState("");
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState(false);
  const [tries, setTries] = useState(0);
  const regions = useRef<string[]>([]);

  const load = useCallback(() => {
    setError(null);
    return api.notesList({ q, kind, region, status }).then((d) => { if (!regions.current.length || d.regions.length > regions.current.length) regions.current = d.regions; setData(d); }).catch((e) => setError(errorMessage(e)));
  }, [q, kind, region, status]);
  useEffect(() => { const t = setTimeout(load, q ? 250 : 0); return () => clearTimeout(t); }, [load, tries, q]);
  useEffect(() => {
    if (!data?.items.some((r) => r.status === "processing")) return;
    const t = setInterval(load, 2500);
    return () => clearInterval(t);
  }, [data, load]);

  return (
    <AdminFrame title="Notes" sub="Lecture notes and dissection guides: upload, preview, publish, edit and keep every version." wide>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1 sm:max-w-xs">
          <Search size={15} strokeWidth={1.5} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted" aria-hidden />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search title or region" aria-label="Search notes"
            className="h-9 w-full rounded-md border border-line-strong bg-surface pl-9 pr-3 text-[14px] text-ink placeholder:text-muted" />
        </div>
        <Select aria-label="Type" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">All types</option><option value="note">Lecture notes</option><option value="guide">Dissection guides</option>
        </Select>
        <Select aria-label="Region" value={region} onChange={(e) => setRegion(e.target.value)}>
          <option value="">All regions</option>{regions.current.map((r) => <option key={r} value={r}>{r}</option>)}
        </Select>
        <Select aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option>
          {["published", "ready", "processing", "archived"].map((s) => <option key={s} value={s}>{s[0].toUpperCase() + s.slice(1)}</option>)}
        </Select>
        <Button className="ml-auto" onClick={() => setOpen(true)}><Upload size={15} strokeWidth={1.5} aria-hidden /> Upload</Button>
      </div>
      {error ? <ErrorLine message={error} retry={() => setTries((t) => t + 1)} /> : !data ? (
        <div className="space-y-2">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-14 !rounded-xl" />)}</div>
      ) : data.items.length === 0 ? <Notice>Nothing matches. Clear a filter or upload a file.</Notice> : (
        <ul className="overflow-hidden rounded-xl border border-line bg-surface" aria-label="Documents">
          <li aria-hidden className="hidden grid-cols-[minmax(0,1fr)_130px_70px_110px_110px_70px] gap-3 border-b border-line bg-surface-2 px-4 py-2 text-[12px] font-medium uppercase tracking-wide text-muted md:grid">
            <span>Title</span><span>Region</span><span>Version</span><span>Status</span><span>Updated</span><span className="text-right">Access</span>
          </li>
          {data.items.map((r) => {
            const body = (
              <>
                <span className="min-w-0">
                  <span className="block text-[15px] md:truncate font-medium text-ink">{r.title}</span>
                  <span className="block text-[12px] text-muted">{r.kind === "guide" ? "Dissection guide" : "Lecture notes"}{r.note ? ` · ${r.note}` : ""}</span>
                </span>
                <span className="text-[14px] text-body-2 max-md:hidden">{r.region}</span>
                <span className="text-[14px] text-body-2 max-md:hidden">v{r.version}</span>
                <span><StatusChip status={r.status} /></span>
                <span className="text-[13px] text-muted max-md:hidden">{r.updated_at ? formatDate(r.updated_at, { month: "short", day: "numeric", year: "numeric" }) : ""}</span>
                <span className="text-right text-[14px] text-body-2 max-md:hidden">{r.access_count}</span>
              </>
            );
            const cls = "grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 border-b border-line px-4 py-3 last:border-b-0 md:grid-cols-[minmax(0,1fr)_130px_70px_110px_110px_70px]";
            return (
              <li key={r.id}>
                {r.id.startsWith("v1:") ? <div className={cls}>{body}</div> : <Link to={`/admin/notes/${encodeURIComponent(r.id)}`} className={`${cls} hover:bg-surface-2`}>{body}</Link>}
              </li>
            );
          })}
        </ul>
      )}
      <p className="mt-3 text-[13px] text-muted">{data ? `${data.total} document${data.total === 1 ? "" : "s"}` : ""}</p>
      <UploadDialog open={open} onOpenChange={setOpen} />
    </AdminFrame>
  );
}
