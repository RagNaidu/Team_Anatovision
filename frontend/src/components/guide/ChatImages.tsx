import { useState } from "react";
import type { SlideImage } from "@/lib/types";
import { imageSrc } from "@/lib/api";
import { Lightbox } from "./Lightbox";
import { MarkOverlay } from "./MarkedImage";

/** Image cards under a chat answer that used dissection-guide slides: a thumbnail with that step's approved marks; tap opens the lightbox (arrows move between the cards). */
export function ChatImages({ images }: { images: SlideImage[] }) {
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);
  if (!images.length) return null;
  return (
    <section className="mt-4" aria-label="Slide images from the dissection guide">
      <ul className="flex gap-3 overflow-x-auto pb-1">
        {images.map((im, i) => {
          const w = im.w || 1280, h = im.h || 720;
          return (
            <li key={`${im.slide}-${i}`} className="w-[190px] shrink-0">
              <button type="button" onClick={() => { setIdx(i); setOpen(true); }} aria-label={`Enlarge ${im.alt}`}
                className="block w-full cursor-zoom-in overflow-hidden rounded-xl border border-line bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
                <span className="relative block" style={{ aspectRatio: `${w} / ${h}` }}>
                  <img src={imageSrc(im.thumb_url)} alt={im.alt} loading="lazy" width={w} height={h} className="absolute inset-0 h-full w-full object-contain" />
                  <MarkOverlay w={w} h={h} marks={im.marks} step={im.step ?? null} />
                </span>
              </button>
              <p className="mt-1 text-[12px] text-muted">{im.step !== null && im.step !== undefined ? `Step ${im.step + 1} · ` : ""}Slide {im.slide}</p>
            </li>
          );
        })}
      </ul>
      <Lightbox images={images} index={idx} onIndex={setIdx} open={open} onClose={() => setOpen(false)} />
    </section>
  );
}
