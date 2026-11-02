import { useEffect, useState } from "react";
import { Lock } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { Student } from "@/lib/types";
import { useData } from "@/state/data";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Notice, Skeleton } from "@/components/ui/misc";
import { cn } from "@/lib/utils";
import { AdminFrame, ErrorLine } from "./shared";

export default function Access() {
  const { scope, scopeError } = useData();
  const [students, setStudents] = useState<Student[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [lectures, setLectures] = useState<string[]>([]);
  const [guides, setGuides] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    let live = true;
    setError(null);
    api.adminStudents().then((s) => { if (live) { setStudents(s); setSel((cur) => cur ?? s[0]?.id ?? null); } }).catch((e) => live && setError(errorMessage(e)));
    return () => { live = false; };
  }, [tries]);
  const student = students?.find((s) => s.id === sel) ?? null;
  useEffect(() => { if (student) { setLectures(student.lecture_ids); setGuides(student.guide_ids); setSaved(null); setSaveError(null); } }, [student?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const allL = scope?.lectures.map((l) => l.id) ?? [];
  const allG = scope?.guides.map((g) => g.id) ?? [];
  const toggle = (arr: string[], set: (a: string[]) => void, id: string, on: boolean) => { set(on ? [...arr, id] : arr.filter((x) => x !== id)); setSaved(null); };

  async function save() {
    if (!student) return;
    setBusy(true); setSaveError(null); setSaved(null);
    try {
      await api.adminSetAccess(student.id, lectures, guides);
      setStudents((ss) => ss?.map((s) => (s.id === student.id ? { ...s, lecture_ids: lectures, guide_ids: guides } : s)) ?? null);
      setSaved(`Saved. ${student.name} sees the change on their next request.`);
    } catch (e) { setSaveError(errorMessage(e)); } finally { setBusy(false); }
  }

  return (
    <AdminFrame title="Access" sub="Choose which lectures and dissection guides each student can open." wide>
      {error || scopeError ? <ErrorLine message={(error ?? scopeError)!} retry={() => setTries((t) => t + 1)} /> : !students || !scope ? (
        <div className="grid gap-6 md:grid-cols-[240px_1fr]"><Skeleton className="h-40 !rounded-xl" /><Skeleton className="h-64 !rounded-xl" /></div>
      ) : students.length === 0 ? <Notice>There are no students yet.</Notice> : (
        <div className="grid gap-6 md:grid-cols-[240px_minmax(0,1fr)]">
          <ul className="space-y-1.5" aria-label="Students">
            {students.map((s) => (
              <li key={s.id}>
                <button type="button" onClick={() => setSel(s.id)} aria-pressed={sel === s.id}
                  className={cn("w-full rounded-xl border px-4 py-3 text-left transition-colors duration-150 hover:bg-surface-2", sel === s.id ? "border-accent bg-surface-2" : "border-line bg-surface")}>
                  <span className="block text-[15px] font-medium">{s.name}</span>
                  <span className="block text-[12px] text-muted">{s.username} · {s.lecture_ids.length} lectures · {s.guide_ids.length} guides</span>
                </button>
              </li>
            ))}
          </ul>
          {student && (
            <section className="rounded-xl border border-line bg-surface p-5" aria-label={`Access for ${student.name}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="font-serif text-[22px] font-semibold">{student.name}</h2>
                <Button size="sm" variant="outline" onClick={() => { setLectures(allL); setGuides(allG); setSaved(null); }}>Grant all</Button>
              </div>
              <fieldset className="mt-4">
                <legend className="mb-1.5 text-[14px] font-medium text-body-2">Lectures</legend>
                <ul className="grid gap-1 sm:grid-cols-2">
                  {scope.lectures.map((l) => (
                    <li key={l.id}><label className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-[14px] hover:bg-surface-2">
                      <Checkbox checked={lectures.includes(l.id)} onCheckedChange={(c) => toggle(lectures, setLectures, l.id, c === true)} aria-label={l.title} /> {l.title}
                    </label></li>
                  ))}
                </ul>
              </fieldset>
              <fieldset className="mt-4">
                <legend className="mb-1.5 text-[14px] font-medium text-body-2">Dissection guides</legend>
                <ul className="grid gap-1 sm:grid-cols-2">
                  {scope.guides.map((g) => (
                    <li key={g.id}><label className="flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 text-[14px] hover:bg-surface-2">
                      <Checkbox checked={guides.includes(g.id)} onCheckedChange={(c) => toggle(guides, setGuides, g.id, c === true)} aria-label={`Class ${g.class_number} ${g.title}`} />
                      <span><span className="serif-label mr-1.5">Class {g.class_number}</span>{g.title}</span>
                      {g.lecture_ids.length === 0 && <Lock size={12} strokeWidth={1.5} className="text-muted" aria-label="Not matched to a lecture" />}
                    </label></li>
                  ))}
                </ul>
              </fieldset>
              <div className="mt-5 flex flex-wrap items-center gap-3">
                <Button onClick={() => void save()} disabled={busy}>{busy ? "Saving…" : "Save"}</Button>
                <span aria-live="polite" className="text-[13px]">{saved && <span className="text-ok">{saved}</span>}{saveError && <span role="alert" className="text-accent">{saveError}</span>}</span>
              </div>
            </section>
          )}
        </div>
      )}
    </AdminFrame>
  );
}
