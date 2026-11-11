import { useState } from "react";
import type { Mark, SlideImage } from "@/lib/types";
import { imageSrc } from "@/lib/api";
import { cn } from "@/lib/utils";

const INK = "#111111";
const GOLD = "#FFD60A";
type Pt = [number, number];
const pt = (v: unknown): Pt => { const a = (v as number[]) ?? [0, 0]; return [Number(a[0]) || 0, Number(a[1]) || 0]; };
const num = (v: unknown) => Number(v) || 0;

/** The marks of one step: marks with no step are always shown. step = null shows every mark (no step selected). */
export function visibleMarks(marks: Mark[], step: number | null | undefined): Mark[] {
  return step === null || step === undefined ? marks : marks.filter((m) => m.step === null || m.step === step);
}

/** Scale a normalised (0-1) point to the image's own pixel space. Exported for tests. */
export function toPx(p: Pt, w: number, h: number): Pt { return [p[0] * w, p[1] * h]; }

function Arrow({ from, to, u }: { from: Pt; to: Pt; u: number }) {
  const [dx, dy] = [to[0] - from[0], to[1] - from[1]];
  const len = Math.hypot(dx, dy) || 1;
  const [ux, uy] = [dx / len, dy / len];
  const head = 7 * u, half = 3.6 * u;
  const base: Pt = [to[0] - ux * head, to[1] - uy * head];
  const tri = `${to[0]},${to[1]} ${base[0] - uy * half},${base[1] + ux * half} ${base[0] + uy * half},${base[1] - ux * half}`;
  return (
    <g>
      <line x1={from[0]} y1={from[1]} x2={base[0]} y2={base[1]} stroke={INK} strokeWidth={3.6 * u} strokeLinecap="round" />
      <polygon points={tri} fill={INK} stroke={INK} strokeWidth={2 * u} strokeLinejoin="round" />
      <line x1={from[0]} y1={from[1]} x2={base[0]} y2={base[1]} stroke={GOLD} strokeWidth={1.8 * u} strokeLinecap="round" />
      <polygon points={tri} fill={GOLD} />
    </g>
  );
}

function Pin({ x, y, n, text, u, w }: { x: number; y: number; n: number; text: string; u: number; w: number }) {
  const fs = 10 * u, r = 7.6 * u;
  const tw = Math.min(text.length, 40) * fs * 0.56 + 2.4 * fs;
  const left = x + r + tw + 2 * u > w;
  const bx = left ? x - r - 1.5 * u - tw : x + r + 1.5 * u;
  return (
    <g>
      {text && <>
        <rect x={bx} y={y - fs * 0.95} width={tw} height={fs * 1.9} rx={fs * 0.4} fill="rgba(17,17,17,0.86)" />
        <text x={bx + 1.2 * fs} y={y + fs * 0.34} fontSize={fs} fill="#fff" fontFamily="Inter, system-ui, sans-serif">{text.length > 40 ? text.slice(0, 39) + "…" : text}</text>
      </>}
      <circle cx={x} cy={y} r={r} fill={GOLD} stroke={INK} strokeWidth={1.4 * u} />
      <text x={x} y={y + fs * 0.36} fontSize={fs} fontWeight={700} textAnchor="middle" fill={INK} fontFamily="Inter, system-ui, sans-serif">{n}</text>
    </g>
  );
}

/** The marks drawn as SVG in the image's own pixel space: the SVG scales with the picture (and with zoom), so a mark stays on its spot at any size. */
export function MarkOverlay({ w, h, marks, step, selectedId, className }: { w: number; h: number; marks: Mark[]; step?: number | null; selectedId?: string | null; className?: string }) {
  const W = w || 1280, H = h || 720, u = W / 400;
  const shown = visibleMarks(marks, step);
  let pin = 0;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className={cn("pointer-events-none absolute inset-0 h-full w-full", className)} aria-hidden data-marks={shown.length}>
      <g key={`step-${step ?? "all"}`} className="mark-fade">
        {shown.map((m) => {
          const g = m.geom;
          const sel = selectedId === m.id, dim = !!selectedId && !sel;
          let el: React.ReactNode = null;
          if (m.kind === "arrow") el = <Arrow from={toPx(pt(g.from), W, H)} to={toPx(pt(g.to), W, H)} u={u} />;
          else if (m.kind === "cut") {
            const pts = ((g.points as number[][]) ?? []).map((p) => toPx(pt(p), W, H).join(",")).join(" ");
            el = <g fill="none" strokeLinecap="round" strokeLinejoin="round"><polyline points={pts} stroke={INK} strokeWidth={3.6 * u} /><polyline points={pts} stroke={GOLD} strokeWidth={1.8 * u} strokeDasharray={`${5 * u} ${3.5 * u}`} /></g>;
          } else if (m.kind === "highlight") {
            const c = toPx([num(g.cx), num(g.cy)], W, H);
            el = <g fill="rgba(255,214,10,0.12)"><ellipse cx={c[0]} cy={c[1]} rx={num(g.rx) * W} ry={num(g.ry) * H} stroke={INK} strokeWidth={3.6 * u} /><ellipse cx={c[0]} cy={c[1]} rx={num(g.rx) * W} ry={num(g.ry) * H} stroke={GOLD} strokeWidth={1.8 * u} /></g>;
          } else {
            pin += 1;
            const c = toPx([num(g.x), num(g.y)], W, H);
            el = <Pin x={c[0]} y={c[1]} n={pin} text={m.text} u={u} w={W} />;
          }
          return <g key={m.id} data-mark={m.kind} opacity={dim ? 0.35 : 1} filter={sel ? "drop-shadow(0 0 6px #fff)" : undefined}>{el}</g>;
        })}
      </g>
    </svg>
  );
}

/** A slide image with its marks. Reserves the picture's shape before it loads (no jump) and loads lazily. */
export function MarkedImage({ image, step, className, eager, onLoad, maxVh = 100 }: { image: SlideImage; step?: number | null; className?: string; eager?: boolean; onLoad?: () => void; maxVh?: number }) {
  const [ok, setOk] = useState(true);
  const w = image.w || 1280, h = image.h || 720;
  return (
    <div className={cn("relative mx-auto w-full overflow-hidden rounded-xl border border-line bg-white", className)} style={{ aspectRatio: `${w} / ${h}`, maxWidth: `calc((${maxVh}vh - 3rem) * ${w} / ${h})` }}>
      {ok ? <img src={imageSrc(image.url)} alt={image.alt} width={w} height={h} loading={eager ? "eager" : "lazy"} decoding="async" onError={() => setOk(false)} onLoad={onLoad} className="absolute inset-0 h-full w-full object-contain" />
        : <div className="absolute inset-0 flex items-center justify-center text-[13px] text-muted">This image could not be loaded.</div>}
      <MarkOverlay w={w} h={h} marks={image.marks} step={step} />
    </div>
  );
}
