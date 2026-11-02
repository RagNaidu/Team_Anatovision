import { useEffect, useRef, useState } from "react";
import { api, askStatusAvailable } from "@/lib/api";

export const STAGE_LABELS: Record<string, string> = {
  searching: "Searching your notes",
  reading: "Checking sources",
  writing: "Writing answer",
  checking: "Checking answer",
};
const ORDER = ["searching", "reading", "writing", "checking"];

export interface StageView { key: string; label: string; state: "done" | "current"; seconds: number | null }

/**
 * Real stages only, from GET /api/ask/status/{request_id} (about once a second; the stage word is all the backend returns).
 * `available` stays false, so the UI shows just the quiet row with no chevron, unless the backend really offers the endpoint.
 * A 404 before the POST registered the id counts as "searching" (as the contract says). Seconds are measured here, between the
 * moments a stage was first seen; a stage that was never seen is never shown.
 */
export function useAskProgress(requestId: string | null, active: boolean) {
  const [available, setAvailable] = useState(false);
  const [stages, setStages] = useState<StageView[]>([]);
  const seen = useRef<{ key: string; at: number | null }[]>([]);

  useEffect(() => {
    if (!active || !requestId) return;
    let live = true;
    const t0 = Date.now();
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
      const now = Date.now();
      const key = st?.stage ?? "searching";
      if (ORDER.includes(key) && !seen.current.some((s) => s.key === key)) {
        // the first stage seen started with the request; later ones started when first noticed
        seen.current.push({ key, at: seen.current.length === 0 ? (key === "searching" ? t0 : null) : now });
      }
      const list = seen.current;
      const done = key === "done";
      const views: StageView[] = list.map((s, i) => {
        const next = list[i + 1];
        const current = i === list.length - 1 && !done;
        const end = next ? next.at : now;
        return {
          key: s.key,
          label: STAGE_LABELS[s.key] ?? s.key,
          state: current ? "current" : "done",
          seconds: current || s.at === null || end === null ? null : Math.round((end - s.at) / 100) / 10,
        };
      });
      setAvailable(true);
      setStages(views);
      if (!done) timer = setTimeout(tick, 700);
    };
    timer = setTimeout(tick, 350);
    return () => { live = false; clearTimeout(timer); };
  }, [requestId, active]);

  return { available, stages };
}
