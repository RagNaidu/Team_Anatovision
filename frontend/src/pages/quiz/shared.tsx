import type { ReactNode } from "react";
import { Globe } from "lucide-react";
import { cn, store } from "@/lib/utils";
import type { QuizBuildBody } from "@/lib/types";

export const LAST_BUILD_KEY = "av_last_build";
export const rememberBuild = (b: QuizBuildBody) => store.set(LAST_BUILD_KEY, b);
export const lastBuild = () => store.get<QuizBuildBody | null>(LAST_BUILD_KEY, null);

export function QuizFrame({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="scroll-quiet h-full overflow-y-auto">
      <div className={cn("mx-auto w-full px-6 py-8 max-lg:px-4", wide ? "max-w-[840px]" : "max-w-[720px]")}>{children}</div>
    </div>
  );
}

/** Thin segmented progress: answered segments filled, the current one outlined. */
export function SegBar({ length, answered, current }: { length: number; answered: (i: number) => boolean; current?: number }) {
  return (
    <div className="flex gap-1" aria-hidden>
      {Array.from({ length }).map((_, i) => (
        <span key={i} className={cn("h-1.5 flex-1 rounded-full transition-colors duration-200", answered(i) ? "bg-accent" : "bg-line-strong", current === i && !answered(i) && "bg-accent/40")} />
      ))}
    </div>
  );
}

/** Every question built from the web says so: it is not from Dr. Inglis's notes (the source is Wikipedia, CC BY-SA 4.0). */
export function WebNote({ note }: { note: string | null }) {
  return (
    <p className="mb-3 inline-flex items-center gap-1.5 rounded-full bg-warn-soft px-3 py-1 text-[13px] font-medium text-warn">
      <Globe size={13} strokeWidth={1.75} aria-hidden /> {note ?? "Not from course notes"} <span className="font-normal opacity-80">· Wikipedia</span>
    </p>
  );
}
