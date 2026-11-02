import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "@/lib/api";
import type { Student } from "@/lib/types";
import { useAuth } from "@/state/auth";
import { Button } from "@/components/ui/button";
import { Notice, Skeleton } from "@/components/ui/misc";
import { cn } from "@/lib/utils";
import { AdminFrame, ErrorLine } from "./shared";

export default function PreviewPicker() {
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [students, setStudents] = useState<Student[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [choice, setChoice] = useState("full");
  const [busy, setBusy] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    let live = true;
    setError(null);
    api.adminStudents().then((s) => live && setStudents(s)).catch((e) => live && setError(errorMessage(e)));
    return () => { live = false; };
  }, [tries]);

  async function start() {
    setBusy(true); setStartError(null);
    try { await api.adminPreview(choice); await refresh(); navigate("/ask"); } catch (e) { setStartError(errorMessage(e)); setBusy(false); }
  }
  const options = [{ id: "full", title: "Full access", sub: "Every lecture and every dissection guide." }, ...(students ?? []).map((s) => ({ id: s.id, title: s.name, sub: `${s.username} · ${s.lecture_ids.length} lectures · ${s.guide_ids.length} guides` }))];

  return (
    <AdminFrame title="Preview as student" sub="See the app exactly as a student does. Nothing you do is saved to a student's record.">
      {error ? <ErrorLine message={error} retry={() => setTries((t) => t + 1)} /> : !students ? <Skeleton className="h-48 !rounded-xl" /> : (
        <>
          <fieldset>
            <legend className="sr-only">Preview as</legend>
            <div className="space-y-2" role="radiogroup" aria-label="Preview as">
              {options.map((o) => (
                <button key={o.id} type="button" role="radio" aria-checked={choice === o.id} onClick={() => setChoice(o.id)}
                  className={cn("flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left transition-colors duration-150", choice === o.id ? "border-accent bg-accent-soft" : "border-line bg-surface hover:bg-surface-2")}>
                  <span className={cn("flex h-5 w-5 shrink-0 items-center justify-center rounded-full border", choice === o.id ? "border-accent" : "border-line-strong")} aria-hidden>
                    {choice === o.id && <span className="h-2.5 w-2.5 rounded-full bg-accent" />}
                  </span>
                  <span><span className="block text-[15px] font-medium">{o.title}</span><span className="block text-[13px] text-muted">{o.sub}</span></span>
                </button>
              ))}
            </div>
          </fieldset>
          {startError && <Notice tone="error" className="mt-4">{startError}</Notice>}
          <Button size="lg" className="mt-6" onClick={() => void start()} disabled={busy}>{busy ? "Starting…" : "Start preview"}</Button>
        </>
      )}
    </AdminFrame>
  );
}
