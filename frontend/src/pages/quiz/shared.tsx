import type { ReactNode } from "react";
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
