import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowUp, ArrowDown, Circle, MousePointer2, MoveUpRight, Redo2, Spline, Tag, Trash2, Undo2 } from "lucide-react";
import { api, errorMessage, imageSrc } from "@/lib/api";
import type { AnnGuide, AnnStation, Mark, MarkKind, SlideImage } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { Notice, Select, Skeleton } from "@/components/ui/misc";
import { MarkedImage, MarkOverlay } from "@/components/guide/MarkedImage";
import { cn } from "@/lib/utils";

type Tool = "view" | MarkKind;
type P = [number, number];
type Geom = Record<string, unknown>;
const TOOLS: { id: Tool; label: string; icon: typeof Circle }[] = [
  { id: "view", label: "Select", icon: MousePointer2 }, { id: "arrow", label: "Arrow", icon: MoveUpRight }, { id: "cut", label: "Cut line", icon: Spline },
  { id: "highlight", label: "Circle", icon: Circle }, { id: "label", label: "Label pin", icon: Tag },
];
const KIND_NAME: Record<MarkKind, string> = { arrow: "Arrow", cut: "Cut line", highlight: "Circle", label: "Label pin" };
const SOURCE_NAME: Record<string, string> = { auto: "from slide", ocr: "from text in picture" };
const r4 = (n: number) => Math.round(Math.min(1, Math.max(0, n)) * 10000) / 10000;
const pt = (v: unknown): P => { const a = (v as number[]) ?? [0, 0]; return [Number(a[0]) || 0, Number(a[1]) || 0]; };
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));

/** Move a whole mark by (dx, dy), keeping it on the picture. */
export function translate(kind: MarkKind, g: Geom, dx: number, dy: number): Geom {
  const mv = (p: P): number[] => [r4(p[0] + dx), r4(p[1] + dy)];
  if (kind === "arrow") return { from: mv(pt(g.from)), to: mv(pt(g.to)) };
  if (kind === "cut") return { points: ((g.points as number[][]) ?? []).map((p) => mv(pt(p))) };
  if (kind === "highlight") return { cx: r4(Number(g.cx) + dx), cy: r4(Number(g.cy) + dy), rx: g.rx, ry: g.ry };
  return { x: r4(Number(g.x) + dx), y: r4(Number(g.y) + dy) };
}

/** The drag handles of a mark: where they are, and what dragging one to (x, y) does to the geometry. */
export function handlesOf(kind: MarkKind, g: Geom): { id: string; at: P }[] {
  if (kind === "arrow") return [{ id: "from", at: pt(g.from) }, { id: "to", at: pt(g.to) }];
  if (kind === "cut") return ((g.points as number[][]) ?? []).map((p, i) => ({ id: `p${i}`, at: pt(p) }));
  if (kind === "highlight") { const [cx, cy, rx, ry] = [Number(g.cx), Number(g.cy), Number(g.rx), Number(g.ry)]; return [{ id: "e", at: [cx + rx, cy] }, { id: "w", at: [cx - rx, cy] }, { id: "n", at: [cx, cy - ry] }, { id: "s", at: [cx, cy + ry] }]; }
  return [];
}
export function dragHandle(kind: MarkKind, g: Geom, handle: string, x: number, y: number): Geom {
  if (kind === "arrow") return { ...g, [handle]: [r4(x), r4(y)] };
  if (kind === "cut") { const pts = clone((g.points as number[][]) ?? []); pts[Number(handle.slice(1))] = [r4(x), r4(y)]; return { points: pts }; }
  if (kind === "highlight") {
    const [cx, cy] = [Number(g.cx), Number(g.cy)];
    if (handle === "e" || handle === "w") return { ...g, rx: Math.max(0.006, r4(Math.abs(x - cx))) };
    return { ...g, ry: Math.max(0.006, r4(Math.abs(y - cy))) };
  }
  return g;
}

type Live = Record<string, Geom>;
interface Cmd { label: string; undo: () => Promise<void>; redo: () => Promise<void> }

function Canvas({ image, tool, step, selectedId, onSelect, live, onLive, onCommit, onCreate }: {
  image: SlideImage; tool: Tool; step: number | null; selectedId: string | null; onSelect: (id: string | null) => void; live: Live; onLive: (id: string, g: Geom | null) => void;
  onCommit: (m: Mark, before: Geom, after: Geom) => void; onCreate: (kind: MarkKind, geom: Geom, text?: string) => void;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const drag = useRef<{ id: string; mode: "move" | string; from: P; orig: Geom; kind: MarkKind } | null>(null);
  const nudgeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nudgeBase = useRef<Geom | null>(null);
  const [start, setStart] = useState<P | null>(null);
  const [cur, setCur] = useState<P | null>(null);
  const [pts, setPts] = useState<P[]>([]);
  const [pin, setPin] = useState<P | null>(null);
  const [text, setText] = useState("");
  useEffect(() => { setStart(null); setCur(null); setPts([]); setPin(null); }, [tool, image.slide, image.crop]);
  const w = image.w || 1280, h = image.h || 720, u = w / 400;
  const marks = image.marks.map((m) => (live[m.id] ? { ...m, geom: live[m.id] } : m));
  const selected = marks.find((m) => m.id === selectedId) ?? null;
  const norm = (e: React.PointerEvent | React.MouseEvent): P => { const r = ref.current!.getBoundingClientRect(); return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))]; };
  const finishCut = () => { if (pts.length >= 2) onCreate("cut", { points: pts.map((p) => [r4(p[0]), r4(p[1])]) }); setPts([]); setCur(null); };

  function down(e: React.PointerEvent) {
    if (!ref.current) return;
    const p = norm(e);
    if (tool === "arrow" || tool === "highlight") { (e.target as Element).setPointerCapture?.(e.pointerId); setStart(p); setCur(p); }
    else if (tool === "cut") setPts((a) => [...a, p]);
    else if (tool === "label") setPin(p);
    else onSelect(null);
  }
  function move(e: React.PointerEvent) {
    if (!ref.current) return;
    if (drag.current) {
      const p = norm(e), d = drag.current;
      onLive(d.id, d.mode === "move" ? translate(d.kind, d.orig, p[0] - d.from[0], p[1] - d.from[1]) : dragHandle(d.kind, d.orig, d.mode, p[0], p[1]));
    } else if (start || pts.length) setCur(norm(e));
  }
  function up(e: React.PointerEvent) {
    if (drag.current) {
      const d = drag.current; drag.current = null;
      const m = image.marks.find((x) => x.id === d.id);
      const after = live[d.id];
      if (m && after && JSON.stringify(after) !== JSON.stringify(d.orig)) onCommit(m, d.orig, after); else onLive(d.id, null);
      return;
    }
    if (!start || !ref.current) return;
    const end = norm(e);
    if (tool === "arrow" && Math.hypot(end[0] - start[0], end[1] - start[1]) > 0.012) onCreate("arrow", { from: [r4(start[0]), r4(start[1])], to: [r4(end[0]), r4(end[1])] });
    if (tool === "highlight") {
      const rx = Math.abs(end[0] - start[0]) / 2, ry = Math.abs(end[1] - start[1]) / 2;
      if (rx > 0.006 && ry > 0.006) onCreate("highlight", { cx: r4((start[0] + end[0]) / 2), cy: r4((start[1] + end[1]) / 2), rx: r4(rx), ry: r4(ry) });
    }
    setStart(null); setCur(null);
  }
  function startDrag(e: React.PointerEvent, m: Mark, mode: string) {
    if (tool !== "view") return;
    e.stopPropagation();
    (e.currentTarget as Element).setPointerCapture?.(e.pointerId);
    onSelect(m.id);
    drag.current = { id: m.id, mode, from: norm(e), orig: clone(m.geom), kind: m.kind };
  }
  function onKey(e: React.KeyboardEvent) {
    if (!selected) return;
    if (e.key === "Escape") { onSelect(null); return; }
    const step_ = e.shiftKey ? 0.01 : 0.002;
    const d: Record<string, P> = { ArrowLeft: [-step_, 0], ArrowRight: [step_, 0], ArrowUp: [0, -step_], ArrowDown: [0, step_] };
    if (!d[e.key]) return;
    e.preventDefault();
    const base = nudgeBase.current ?? clone(selected.geom);
    nudgeBase.current = base;
    const next = translate(selected.kind, live[selected.id] ?? selected.geom, d[e.key][0], d[e.key][1]);
    onLive(selected.id, next);
    if (nudgeTimer.current) clearTimeout(nudgeTimer.current);
    nudgeTimer.current = setTimeout(() => { const m = image.marks.find((x) => x.id === selected.id); if (m && nudgeBase.current) onCommit(m, nudgeBase.current, next); nudgeBase.current = null; }, 600);
  }
  const hit = { fill: "none", stroke: "transparent", strokeWidth: 9 * u, pointerEvents: "stroke" as const, style: { cursor: tool === "view" ? "move" : "crosshair" } };
  const P = (p: P) => [p[0] * w, p[1] * h] as P;
  const ghost = start && cur ? (tool === "arrow" ? <line x1={start[0] * w} y1={start[1] * h} x2={cur[0] * w} y2={cur[1] * h} stroke="#FFD60A" strokeWidth={1.8 * u} /> :
    <ellipse cx={(start[0] + cur[0]) / 2 * w} cy={(start[1] + cur[1]) / 2 * h} rx={Math.abs(cur[0] - start[0]) / 2 * w} ry={Math.abs(cur[1] - start[1]) / 2 * h} fill="rgba(255,214,10,0.15)" stroke="#FFD60A" strokeWidth={1.8 * u} />) : null;
  return (
    <div>
      <div className="relative mx-auto overflow-hidden rounded-xl border border-line bg-white outline-none focus-visible:ring-2 focus-visible:ring-accent" tabIndex={0} onKeyDown={onKey}
        style={{ aspectRatio: `${w} / ${h}`, maxWidth: `calc((100vh - 14rem) * ${w} / ${h})` }} data-canvas aria-label="Picture with marks. Select a mark, then use the arrow keys to nudge it.">
        <MarkedImage image={{ ...image, marks: [] }} className="!rounded-none !border-0 !max-w-none" eager />
        <MarkOverlay w={w} h={h} marks={marks} step={null} selectedId={selectedId} />
        <svg ref={ref} viewBox={`0 0 ${w} ${h}`} aria-label={`Drawing area for slide ${image.slide}`} role="application" className="absolute inset-0 h-full w-full"
          style={{ cursor: tool === "view" ? "default" : "crosshair", touchAction: tool === "view" ? "pan-y" : "none" }} onPointerDown={down} onPointerMove={move} onPointerUp={up} onDoubleClick={() => tool === "cut" && finishCut()}>
          {tool === "view" && marks.map((m) => {
            const g = m.geom, on = (e: React.PointerEvent) => startDrag(e, m, "move");
            if (m.kind === "arrow") { const a = P(pt(g.from)), b = P(pt(g.to)); return <line key={m.id} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} {...hit} onPointerDown={on} data-hit={m.id} />; }
            if (m.kind === "cut") return <polyline key={m.id} points={((g.points as number[][]) ?? []).map((p) => P(pt(p)).join(",")).join(" ")} {...hit} onPointerDown={on} data-hit={m.id} />;
            if (m.kind === "highlight") return <ellipse key={m.id} cx={Number(g.cx) * w} cy={Number(g.cy) * h} rx={Number(g.rx) * w} ry={Number(g.ry) * h} {...hit} fill="transparent" onPointerDown={on} data-hit={m.id} />;
            const c = P([Number(g.x), Number(g.y)]);
            return <circle key={m.id} cx={c[0]} cy={c[1]} r={8 * u} fill="transparent" style={{ cursor: "move" }} onPointerDown={on} data-hit={m.id} />;
          })}
          {tool === "view" && selected && handlesOf(selected.kind, selected.geom).map((hd) => {
            const c = P(hd.at);
            return <rect key={hd.id} x={c[0] - 3.2 * u} y={c[1] - 3.2 * u} width={6.4 * u} height={6.4 * u} rx={1.2 * u} fill="#fff" stroke="#111" strokeWidth={1.1 * u} style={{ cursor: "grab" }}
              onPointerDown={(e) => startDrag(e, selected, hd.id)} data-handle={hd.id} />;
          })}
          {ghost}
          {pts.length > 0 && <polyline points={[...pts, ...(cur ? [cur] : [])].map((p) => P(p).join(",")).join(" ")} fill="none" stroke="#FFD60A" strokeWidth={1.8 * u} strokeDasharray={`${5 * u} ${3.5 * u}`} />}
          {pin && <circle cx={pin[0] * w} cy={pin[1] * h} r={4 * u} fill="#FFD60A" stroke="#111" strokeWidth={1.2 * u} />}
        </svg>
      </div>
      {tool === "cut" && pts.length > 0 && <p className="mt-2 text-[13px] text-body-2">{pts.length} point{pts.length === 1 ? "" : "s"}. Click to add more. <Button size="sm" onClick={finishCut} disabled={pts.length < 2}>Finish the line</Button> <Button size="sm" variant="ghost" onClick={() => setPts([])}>Cancel</Button></p>}
      {tool === "label" && pin && (
        <form className="mt-2 flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { onCreate("label", { x: r4(pin[0]), y: r4(pin[1]) }, text.trim()); setPin(null); setText(""); } }}>
          <input autoFocus value={text} onChange={(e) => setText(e.target.value)} maxLength={80} placeholder="Text for the pin" aria-label="Text for the pin" className="h-9 w-64 rounded-md border border-line-strong bg-surface px-2.5 text-[14px]" />
          <Button size="sm" type="submit" disabled={!text.trim()}>Add pin</Button><Button size="sm" variant="ghost" type="button" onClick={() => setPin(null)}>Cancel</Button>
          {step !== null && <span className="text-[12px] text-muted">It will belong to step {step + 1}.</span>}
        </form>
      )}
    </div>
  );
}

export default function GuideAnnotations({ guideId }: { guideId: string }) {
  const [data, setData] = useState<AnnGuide | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [si, setSi] = useState(0);
  const [ii, setIi] = useState(0);
  const [tool, setTool] = useState<Tool>("view");
  const [step, setStep] = useState<number | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const [original, setOriginal] = useState(false);
  const [pstep, setPstep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [live, setLive] = useState<Live>({});
  const [undo, setUndo] = useState<Cmd[]>([]);
  const [redo, setRedo] = useState<Cmd[]>([]);
  const [bulk, setBulk] = useState(false);

  const load = useCallback(() => api.annotations(guideId).then((d) => { setData(d); setError(null); }).catch((e) => setError(errorMessage(e))), [guideId]);
  useEffect(() => { void load(); }, [load]);
  useEffect(() => { setIi(0); setSel(null); setStep(null); setPstep(0); setLive({}); setUndo([]); setRedo([]); setOriginal(false); }, [si]);
  useEffect(() => { setSel(null); setLive({}); setOriginal(false); }, [ii]);

  const st: AnnStation | undefined = data?.stations[Math.min(si, (data?.stations.length ?? 1) - 1)];
  const image = st?.images[Math.min(ii, (st?.images.length ?? 1) - 1)];
  const slide = image?.slide ?? 0, crop = image?.crop ?? 1;

  const run = useCallback(async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true); setError(null);
    try { await fn(); await load(); if (ok) setMsg(ok); } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }, [load]);

  // ---- undo / redo: every change the instructor makes is a command that can be taken back (a deleted mark comes back as a draft)
  const push = useCallback((c: Cmd) => { setUndo((u) => [...u.slice(-49), c]); setRedo([]); }, []);
  const doUndo = useCallback(() => { const c = undo[undo.length - 1]; if (!c) return; setUndo(undo.slice(0, -1)); void run(async () => { await c.undo(); setRedo((r) => [...r, c]); }); }, [undo, run]);
  const doRedo = useCallback(() => { const c = redo[redo.length - 1]; if (!c) return; setRedo(redo.slice(0, -1)); void run(async () => { await c.redo(); setUndo((u) => [...u, c]); }); }, [redo, run]);
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") { e.preventDefault(); if (e.shiftKey) doRedo(); else doUndo(); }
      else if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "y") { e.preventDefault(); doRedo(); }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [doUndo, doRedo]);

  const create = useCallback(async (kind: MarkKind, geom: Geom, text?: string) => {
    if (!image) return;
    const body = { slide: image.slide, crop: image.crop ?? 1, kind, geom, text, step };
    setBusy(true); setError(null);
    try {
      const ref = { id: (await api.addMark(guideId, body)).id };
      push({ label: `Add ${KIND_NAME[kind]}`, undo: async () => { await api.deleteMark(guideId, ref.id); }, redo: async () => { ref.id = (await api.addMark(guideId, body)).id; } });
      await load(); setMsg("Added as a draft.");
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  }, [guideId, image, step, load, push]);

  const commitGeom = useCallback(async (m: Mark, before: Geom, after: Geom) => {
    setBusy(true); setError(null);
    try {
      const ref = { id: m.id };
      await api.editMark(guideId, ref.id, { geom: after });
      push({ label: `Move ${KIND_NAME[m.kind]}`, undo: async () => { await api.editMark(guideId, ref.id, { geom: before }); }, redo: async () => { await api.editMark(guideId, ref.id, { geom: after }); } });
      await load();
    } catch (e) { setError(errorMessage(e)); } finally { setLive((l) => { const n = { ...l }; delete n[m.id]; return n; }); setBusy(false); }
  }, [guideId, load, push]);

  const remove = useCallback(async (m: Mark) => {
    const body = { slide: m.slide, crop: m.crop ?? 1, kind: m.kind, geom: m.geom, text: m.text, step: m.step };
    const ref = { id: m.id };
    await run(async () => {
      await api.deleteMark(guideId, ref.id);
      push({ label: `Delete ${KIND_NAME[m.kind]}`, undo: async () => { ref.id = (await api.addMark(guideId, body)).id; }, redo: async () => { await api.deleteMark(guideId, ref.id); } });
    }, "Deleted. Undo brings it back as a draft.");
    setSel(null);
  }, [guideId, run, push]);

  const edit = useCallback((m: Mark, patch: { text?: string; step?: number | null }) => {
    const before = { text: m.text, step: m.step };
    void run(async () => {
      await api.editMark(guideId, m.id, patch);
      push({ label: "Edit", undo: async () => { await api.editMark(guideId, m.id, before); }, redo: async () => { await api.editMark(guideId, m.id, patch); } });
    });
  }, [guideId, run, push]);

  const marks: Mark[] = image?.marks ?? [];
  const nStations = useMemo(() => data?.stations.filter((s) => s.images.length > 0).length ?? 0, [data]);

  if (error && !data) return <Notice tone="error">{error}</Notice>;
  if (!data) return <Skeleton className="h-64 !rounded-xl" />;
  if (!data.rendered) return <Notice>This guide's slides have not been rendered to images yet, so there is nothing to mark. Run scripts/guide_images_build.py.</Notice>;
  if (!st || !image) return <Notice>This guide has no pictures.</Notice>;
  const approvedMarks = marks.filter((m) => m.status === "approved" && !m.flag);
  const previewImage: SlideImage = { ...image, marks: approvedMarks };
  const hasApproved = st.images.some((i) => i.marks.some((m) => m.status === "approved"));
  const drafts = st.images.flatMap((i) => i.marks.filter((m) => m.status === "draft"));
  const flagged = drafts.filter((m) => m.flag);
  const unchecked = st.images.filter((i) => i.confidence === "low" && !i.reviewed);

  return (
    <div className="grid gap-5 lg:grid-cols-[240px_minmax(0,1fr)]" aria-label="Image annotations">
      <nav aria-label="Stations" className="max-h-[70vh] overflow-y-auto rounded-xl border border-line bg-surface p-2">
        <ul className="space-y-1">
          {data.stations.map((s) => (
            <li key={s.index}>
              <button type="button" onClick={() => setSi(data.stations.indexOf(s))} aria-current={s.index === st.index} disabled={s.images.length === 0}
                className={cn("w-full rounded-lg px-3 py-2 text-left text-[14px] disabled:opacity-40", s.index === st.index ? "bg-surface-2 font-medium" : "hover:bg-surface-2")}>
                <span className="block">{s.index + 1}. {s.title}</span>
                <span className="text-[12px] text-muted">{s.images.length === 0 ? "no picture" : `${s.approved} approved · ${s.drafts} draft`}</span>
              </button>
            </li>
          ))}
        </ul>
      </nav>

      <div className="min-w-0">
        {msg && <Notice className="mb-3" action={<Button size="sm" variant="ghost" onClick={() => setMsg(null)}>Dismiss</Button>}>{msg}</Notice>}
        {error && <Notice tone="error" className="mb-3">{error}</Notice>}
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <h2 className="mr-auto font-serif text-[20px] font-semibold">{st.title}</h2>
          <label className="flex cursor-pointer items-center gap-2 text-[14px]"><input type="checkbox" checked={preview} onChange={(e) => { setPreview(e.target.checked); setPstep(0); }} className="accent-[rgb(var(--accent))]" /> Preview as a student sees it</label>
          <Button size="sm" disabled={busy || st.drafts === 0} onClick={() => setBulk(true)}>Approve drafts…</Button>
          <Button size="sm" variant="outline" disabled={busy || st.approved === 0} onClick={() => run(() => api.approveStation(guideId, st.index, false), "Sent back to draft. Students no longer see these marks.")}>Back to draft</Button>
        </div>
        {st.images.length > 1 && (
          <ul className="mb-3 flex gap-2 overflow-x-auto" aria-label="Pictures of this station">
            {st.images.map((im, k) => <li key={`${im.slide}-${im.crop}`}><Button size="sm" variant={k === ii ? "primary" : "outline"} onClick={() => setIi(k)}>Slide {im.slide}{st.images.filter((x) => x.slide === im.slide).length > 1 ? `, picture ${im.crop}` : ""}</Button></li>)}
          </ul>
        )}
        {image.confidence === "low" && (
          <Notice className="mb-3" action={image.reviewed ? <Button size="sm" variant="outline" disabled={busy} onClick={() => run(() => api.reviewCrop(guideId, slide, crop, false), "Students no longer see this picture.")}>Un-check</Button>
            : <Button size="sm" disabled={busy} onClick={() => run(() => api.reviewCrop(guideId, slide, crop, true), "Marked as checked. Students can now see this picture.")}>Mark as checked</Button>}>
            <strong className="font-semibold text-ink">{image.reviewed ? "Checked." : "Needs a look before students see it."}</strong> {image.why || "The crop was not certain."} Use “View original slide” to compare.
          </Notice>
        )}

        {preview ? (
          <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]" aria-label="Student preview">
            <div>
              {!hasApproved && <Notice className="mb-3">Nothing is approved in this station yet, so a student sees the plain picture.</Notice>}
              <ol className="space-y-2">
                {st.steps.map((s, i) => (
                  <li key={i}><button type="button" aria-pressed={i === pstep} onClick={() => setPstep(i)} className={cn("flex w-full gap-3 rounded-xl border px-3 py-2 text-left text-[15px]", i === pstep ? "border-accent bg-accent-soft/50" : "border-transparent hover:bg-surface-2")}>
                    <span className="mt-[2px] flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-line-strong text-[12px]">{i + 1}</span>{s}</button></li>
                ))}
              </ol>
            </div>
            <MarkedImage image={previewImage} step={hasApproved ? pstep : null} />
          </div>
        ) : (
          <>
            <div className="mb-3 flex flex-wrap items-center gap-2" role="toolbar" aria-label="Drawing tools">
              {TOOLS.map((t) => (
                <Button key={t.id} size="sm" variant={tool === t.id ? "primary" : "outline"} aria-pressed={tool === t.id} onClick={() => setTool(t.id)}><t.icon size={14} aria-hidden /> {t.label}</Button>
              ))}
              <span className="mx-1 h-5 w-px bg-line" aria-hidden />
              <Button size="sm" variant="outline" disabled={undo.length === 0 || busy} onClick={doUndo} aria-label="Undo"><Undo2 size={14} aria-hidden /> Undo</Button>
              <Button size="sm" variant="outline" disabled={redo.length === 0 || busy} onClick={doRedo} aria-label="Redo"><Redo2 size={14} aria-hidden /> Redo</Button>
              <label className="ml-auto flex items-center gap-2 text-[13px] text-body-2">New marks belong to
                <Select aria-label="Step for new marks" value={step === null ? "" : String(step)} onChange={(e) => setStep(e.target.value === "" ? null : Number(e.target.value))} className="max-w-[220px]">
                  <option value="">The whole station</option>{st.steps.map((s, i) => <option key={i} value={i}>Step {i + 1}: {s.slice(0, 40)}</option>)}
                </Select></label>
              <label className="flex cursor-pointer items-center gap-2 text-[13px]"><input type="checkbox" checked={original} onChange={(e) => setOriginal(e.target.checked)} className="accent-[rgb(var(--accent))]" /> View original slide</label>
            </div>
            {original ? (
              <div>
                <img src={imageSrc(image.original_url ?? "")} alt={`Original slide ${image.slide}`} className="mx-auto w-full max-w-[900px] rounded-xl border border-line bg-white" />
                <p className="mt-2 text-[12px] text-muted">The whole slide, with its step text. Students never see this view. Marks are not drawn here.</p>
              </div>
            ) : (
              <>
                <Canvas image={image} tool={tool} step={step} selectedId={sel} onSelect={setSel} live={live} onLive={(id, g) => setLive((l) => { const n = { ...l }; if (g) n[id] = g; else delete n[id]; return n; })} onCommit={commitGeom} onCreate={(k, g, t) => void create(k, g, t)} />
                <p className="mt-2 text-[12px] text-muted">Select: drag a mark to move it, drag the square handles to resize or reshape, arrow keys nudge (Shift for bigger steps), Delete removes it, Ctrl/Cmd+Z undoes. Draw: drag for an arrow or a circle, click points for a cut line (double-click to finish), click for a label pin. New and edited marks are drafts.</p>
              </>
            )}
          </>
        )}

        <section className="mt-5" aria-label="Marks on this slide">
          <h3 className="font-serif text-[17px] font-semibold">Marks on slide {image.slide}{st.images.filter((x) => x.slide === image.slide).length > 1 ? `, picture ${image.crop}` : ""}</h3>
          {marks.length === 0 ? <p className="mt-1 text-[14px] text-muted">No marks yet. Students see the plain picture.</p> : (
            <ul className="mt-2 space-y-2">
              {marks.map((m, k) => (
                <li key={m.id} className={cn("rounded-xl border bg-surface p-3 text-[14px]", sel === m.id ? "border-accent" : "border-line")} onClick={() => setSel(m.id)}
                  onKeyDown={(e) => { if (e.key === "Delete" && (e.target as HTMLElement).tagName === "LI") void remove(m); }} tabIndex={0}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{KIND_NAME[m.kind]}</span>
                    <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", m.status === "approved" ? "bg-ok-soft text-ok" : "bg-warn-soft text-warn")}>{m.status === "approved" ? "Approved" : "Draft"}</span>
                    {m.source && m.source !== "manual" && <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] text-body-2">{SOURCE_NAME[m.source]}</span>}
                    {m.flag && <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent-soft-ink">Flagged</span>}
                    <span className="text-[12px] text-muted">v{m.version}{m.author ? ` · ${m.author}` : ""}</span>
                    <span className="ml-auto flex gap-1">
                      <button type="button" aria-label="Move up" disabled={k === 0 || busy} className="rounded p-1 hover:bg-surface-2 disabled:opacity-40" onClick={(e) => { e.stopPropagation(); const ids = marks.map((x) => x.id); [ids[k - 1], ids[k]] = [ids[k], ids[k - 1]]; void run(() => api.reorderMarks(guideId, slide, crop, ids)); }}><ArrowUp size={15} /></button>
                      <button type="button" aria-label="Move down" disabled={k === marks.length - 1 || busy} className="rounded p-1 hover:bg-surface-2 disabled:opacity-40" onClick={(e) => { e.stopPropagation(); const ids = marks.map((x) => x.id); [ids[k + 1], ids[k]] = [ids[k], ids[k + 1]]; void run(() => api.reorderMarks(guideId, slide, crop, ids)); }}><ArrowDown size={15} /></button>
                      <button type="button" aria-label={`Delete ${KIND_NAME[m.kind]}`} disabled={busy} className="rounded p-1 text-accent hover:bg-accent-soft" onClick={(e) => { e.stopPropagation(); void remove(m); }}><Trash2 size={15} /></button>
                    </span>
                  </div>
                  {m.flag && <p className="mt-1 text-[13px] text-accent-soft-ink">{m.flag}</p>}
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    {m.kind === "label" && <input defaultValue={m.text} aria-label="Label text" maxLength={80} className="h-8 w-56 rounded-md border border-line-strong bg-bone px-2 text-[13px]"
                      onBlur={(e) => { const v = e.target.value.trim(); if (v && v !== m.text) edit(m, { text: v }); }} />}
                    <Select aria-label="Step this mark belongs to" value={m.step === null ? "" : String(m.step)} onChange={(e) => edit(m, { step: e.target.value === "" ? null : Number(e.target.value) })} className="max-w-[260px]">
                      <option value="">Shown with every step</option>{st.steps.map((s, i) => <option key={i} value={i}>Step {i + 1}: {s.slice(0, 40)}</option>)}
                    </Select>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-[12px] text-muted">{nStations} station{nStations === 1 ? "" : "s"} with pictures. Editing a mark sends it back to draft until you approve the station again.</p>
        </section>
      </div>

      <Dialog open={bulk} onOpenChange={setBulk}>
        <DialogContent title={`Approve the drafts of “${st.title}”`} description="Students will see approved marks as soon as you confirm. Look at what you are approving first." className="max-h-[90dvh] max-w-3xl overflow-y-auto">
          <div className="space-y-4" aria-label="Approval preview">
            <p className="text-[14px]"><strong>{drafts.length - flagged.length}</strong> draft mark{drafts.length - flagged.length === 1 ? "" : "s"} will be approved.{flagged.length > 0 && <> <strong>{flagged.length}</strong> flagged mark{flagged.length === 1 ? " is" : "s are"} left as drafts: fix or delete {flagged.length === 1 ? "it" : "them"} first.</>}</p>
            {unchecked.length > 0 && <Notice>{unchecked.length} picture{unchecked.length === 1 ? " here needs" : "s here need"} a look before students can see {unchecked.length === 1 ? "it" : "them"}: students will not see marks on {unchecked.length === 1 ? "it" : "them"} until the picture is marked as checked.</Notice>}
            {st.images.filter((i) => i.marks.some((m) => m.status === "draft")).map((im) => (
              <figure key={`${im.slide}-${im.crop}`} className="rounded-xl border border-line p-3">
                <figcaption className="mb-2 text-[13px] font-medium">Slide {im.slide}{(im.crop ?? 1) > 1 ? `, picture ${im.crop}` : ""}</figcaption>
                <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
                  <MarkedImage image={{ ...im, marks: im.marks.filter((m) => !m.flag) }} step={null} maxVh={60} />
                  <ul className="space-y-1 text-[13px]">
                    {im.marks.filter((m) => m.status === "draft").map((m) => (
                      <li key={m.id} className={cn("rounded-lg bg-surface-2 px-2 py-1", m.flag && "bg-accent-soft/60")}>{KIND_NAME[m.kind]}{m.text ? `: ${m.text}` : ""}<span className="text-muted"> · {m.step === null ? "every step" : `step ${m.step + 1}`}{m.source !== "manual" ? ` · ${SOURCE_NAME[m.source ?? "auto"]}` : ""}</span>{m.flag && <span className="block text-accent-soft-ink">{m.flag}</span>}</li>
                    ))}
                  </ul>
                </div>
              </figure>
            ))}
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setBulk(false)}>Cancel</Button>
            <Button disabled={busy || drafts.length - flagged.length === 0} onClick={() => { setBulk(false); void run(() => api.approveStation(guideId, st.index, true), `Approved the marks of "${st.title}". Students see them now.`); }}>Approve {drafts.length - flagged.length}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
