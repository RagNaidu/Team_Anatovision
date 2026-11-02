import { useEffect, useRef, useState } from "react";
import { api, askStatusAvailable } from "@/lib/api";

export const STAGE_LABELS: Record<string, string> = {
  searching: "Searching your notes",
  reading: "Reading the sources",
  writing: "Writing the answer",
  checking: "Checking the answer",
};
const ORDER = ["searching", "reading", "writing", "checking"];

export interface StageView { key: string; label: string; state: "done" | "current"; seconds: number | null }

/** Real stages only. `available` stays false (so the UI shows just the quiet row, no chevron) unless the backend reports stages. */
export function useAskProgress(requestId: string | null, active: boolean) {
  const [available, setAvailable] = useState(false);
  const [stages, setStages] = useState<StageView[]>([]);
  const seen = useRef<{ key: string; at: number }[]>([]);

  useEffect(() => {
    if (!active || !requestId) return;
    let live = true;
    seen.current = [];
    setStages([]);
    setAvailable(false);
    let timer: ReturnType<typeof setTimeout>;
    const tick = async () => {
      const ok = await askStatusAvailable();
      if (!live) return;
      if (!ok) { setAvailable(false); return; }
      const st = await api.askStatus(requestId);
      if (!live) return;
      if (st && typeof st.stage === "string") {
        const now = Date.now();
        const key = st.stage;
        if (ORDER.includes(key) && !seen.current.some((s) => s.key === key)) seen.current.push({ key, at: now });
        const server = new Map((st.stages ?? []).map((s) => [s.key, s.seconds ?? null]));
        const views: StageView[] = seen.current.map((s, i) => {
          const isCurrent = i === seen.current.length - 1 && key !== "done";
          const next = seen.current[i + 1];
          const own = server.get(s.key);
          return {
            key: s.key,
            label: STAGE_LABELS[s.key] ?? s.key,
            state: isCurrent ? "current" : "done",
            seconds: isCurrent ? null : own ?? (next ? Math.round((next.at - s.at) / 100) / 10 : Math.round((now - s.at) / 100) / 10),
          };
        });
        setAvailable(true);
        setStages(views);
      }
      timer = setTimeout(tick, 600);
    };
    timer = setTimeout(tick, 250);
    return () => { live = false; clearTimeout(timer); };
  }, [requestId, active]);

  return { available, stages };
}
