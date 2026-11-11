import { useCallback, useEffect, useRef, useState } from "react";
import * as D from "@radix-ui/react-dialog";
import { ChevronLeft, ChevronRight, Minus, Plus, X } from "lucide-react";
import type { SlideImage } from "@/lib/types";
import { imageSrc } from "@/lib/api";
import { MarkOverlay } from "./MarkedImage";

export const DISCLAIMER = "Your cadaver may look different.";
const MIN = 1, MAX = 6;
const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));

/** Full-screen viewer: tap to open, wheel / pinch / buttons to zoom, drag to pan when zoomed, left / right arrows between images, Esc closes.
 *  The marks are an SVG inside the zoomed layer, so they scale with the picture. step = the selected step (marks of that step only). */
export function Lightbox({ images, index, onIndex, open, onClose, step }: { images: SlideImage[]; index: number; onIndex: (i: number) => void; open: boolean; onClose: () => void; step?: number | null }) {
  const [scale, setScale] = useState(1);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const pointers = useRef(new Map<number, { x: number; y: number }>());
  const gesture = useRef<{ d: number; s: number } | null>(null);
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const img = images[index];

  const reset = useCallback(() => { setScale(1); setPos({ x: 0, y: 0 }); }, []);
  useEffect(() => { reset(); }, [index, open, reset]);
  const zoomTo = useCallback((s: number) => { const v = clamp(s, MIN, MAX); setScale(v); if (v === 1) setPos({ x: 0, y: 0 }); }, []);
  const go = useCallback((d: number) => { if (images.length > 1) onIndex((index + d + images.length) % images.length); }, [images.length, index, onIndex]);

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowRight") { e.preventDefault(); go(1); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); go(-1); }
    else if (e.key === "+" || e.key === "=") { e.preventDefault(); zoomTo(scale * 1.4); }
    else if (e.key === "-") { e.preventDefault(); zoomTo(scale / 1.4); }
    else if (e.key === "0") { e.preventDefault(); reset(); }
  }
  function onWheel(e: React.WheelEvent) { zoomTo(scale * Math.exp(-e.deltaY * 0.0022)); }
  function onPointerDown(e: React.PointerEvent) {
    (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 2) {
      const [a, b] = [...pointers.current.values()];
      gesture.current = { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, s: scale };
      drag.current = null;
    } else if (pointers.current.size === 1) drag.current = { x: e.clientX, y: e.clientY, px: pos.x, py: pos.y };
  }
  function onPointerMove(e: React.PointerEvent) {
    if (!pointers.current.has(e.pointerId)) return;
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pointers.current.size === 2 && gesture.current) {
      const [a, b] = [...pointers.current.values()];
      zoomTo(gesture.current.s * (Math.hypot(a.x - b.x, a.y - b.y) / gesture.current.d));
    } else if (drag.current && scale > 1) setPos({ x: drag.current.px + e.clientX - drag.current.x, y: drag.current.py + e.clientY - drag.current.y });
  }
  function onPointerUp(e: React.PointerEvent) {
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) gesture.current = null;
    if (pointers.current.size === 0) drag.current = null;
  }

  if (!img) return null;
  const w = img.w || 1280, h = img.h || 720;
  const btn = "inline-flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-white hover:bg-white/20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-white disabled:opacity-40";
  return (
    <D.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <D.Portal>
        <D.Overlay className="fixed inset-0 z-[60] bg-black/95" />
        <D.Content onKeyDown={onKeyDown} aria-describedby={undefined} className="fixed inset-0 z-[60] flex flex-col text-white outline-none" data-lightbox>
          <header className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0">
              <D.Title className="truncate text-[15px] font-medium">{img.caption}</D.Title>
              <p className="text-[12px] text-white/70">{DISCLAIMER}{images.length > 1 ? ` · ${index + 1} of ${images.length}` : ""}</p>
            </div>
            <div className="flex items-center gap-2">
              <button type="button" className={btn} onClick={() => zoomTo(scale / 1.4)} aria-label="Zoom out" disabled={scale <= MIN}><Minus size={18} /></button>
              <button type="button" className={btn} onClick={() => zoomTo(scale * 1.4)} aria-label="Zoom in" disabled={scale >= MAX}><Plus size={18} /></button>
              <D.Close className={btn} aria-label="Close"><X size={18} /></D.Close>
            </div>
          </header>
          <div className="relative min-h-0 flex-1 select-none overflow-hidden" style={{ touchAction: "none", cursor: scale > 1 ? "grab" : "zoom-in" }}
            onWheel={onWheel} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp}
            onDoubleClick={() => (scale > 1 ? reset() : zoomTo(2.5))}>
            <div className="absolute inset-0 flex items-center justify-center p-2">
              <div className="relative max-h-full max-w-full" style={{ aspectRatio: `${w} / ${h}`, width: `min(100%, calc((100vh - 140px) * ${w} / ${h}))`, transform: `translate(${pos.x}px, ${pos.y}px) scale(${scale})`, transition: pointers.current.size ? "none" : "transform 0.12s ease-out" }}>
                <img src={imageSrc(img.url)} alt={img.alt} width={w} height={h} draggable={false} className="absolute inset-0 h-full w-full rounded-md bg-white object-contain" />
                <MarkOverlay w={w} h={h} marks={img.marks} step={step ?? img.step ?? null} />
              </div>
            </div>
            {images.length > 1 && (
              <>
                <button type="button" onClick={() => go(-1)} aria-label="Previous image" className={`${btn} absolute left-3 top-1/2 -translate-y-1/2`}><ChevronLeft size={20} /></button>
                <button type="button" onClick={() => go(1)} aria-label="Next image" className={`${btn} absolute right-3 top-1/2 -translate-y-1/2`}><ChevronRight size={20} /></button>
              </>
            )}
          </div>
          <footer className="px-4 py-2 text-center text-[12px] text-white/60">Scroll or pinch to zoom, drag to move, arrow keys for the next image, Esc to close.</footer>
        </D.Content>
      </D.Portal>
    </D.Root>
  );
}
