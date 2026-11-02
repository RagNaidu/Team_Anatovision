import { useEffect, useState } from "react";
import { Bar, BarChart, Cell, LabelList, ResponsiveContainer, XAxis, YAxis } from "recharts";
import { api, errorMessage } from "@/lib/api";
import type { AdminStats } from "@/lib/types";
import { Skeleton } from "@/components/ui/misc";
import { AdminFrame, ErrorLine } from "./shared";

const SHADES = ["#8A2D2A", "#9E4642", "#B2605C", "#C47F7A", "#D69D98"];

export default function Overview() {
  const [s, setS] = useState<AdminStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  useEffect(() => {
    let live = true;
    setError(null);
    api.adminStats().then((x) => live && setS(x)).catch((e) => live && setError(errorMessage(e)));
    return () => { live = false; };
  }, [tries]);

  const rc = s?.review_counts;
  const data = rc ? [
    { name: "Confirmed factual", value: rc.confirmed_factual }, { name: "Doubtful", value: rc.doubtful }, { name: "Wording", value: rc.wording },
    { name: "Typos", value: rc.typo }, { name: "Start here", value: rc.start_here },
  ] : [];

  return (
    <AdminFrame title="Overview" sub="What students asked and what still needs your decision.">
      {error ? <ErrorLine message={error} retry={() => setTries((t) => t + 1)} /> : (
        <>
          <dl className="grid gap-3 sm:grid-cols-3">
            {([["Questions in the last 7 days", s?.questions_7d], ["Open flags", s?.flagged_open], ["Web-sourced answers in the last 7 days", s?.web_answers_7d]] as const).map(([label, v]) => (
              <div key={label} className="rounded-xl border border-line bg-surface p-5">
                <dt className="text-[14px] text-muted">{label}</dt>
                <dd className="mt-2 font-serif text-[40px] font-semibold leading-none">{s ? v : <Skeleton className="h-9 w-16" />}</dd>
              </div>
            ))}
          </dl>
          <section className="mt-8 rounded-xl border border-line bg-surface p-5" aria-label="Review breakdown">
            <h2 className="font-serif text-[20px] font-semibold">Fact-check breakdown</h2>
            <p className="serif-label mb-3">AI suggestions waiting for a decision. The AI only flags.</p>
            {!s ? <Skeleton className="h-52" /> : (
              <div className="h-[240px] w-full text-ink" role="img" aria-label={data.map((d) => `${d.name} ${d.value}`).join(", ")}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data} layout="vertical" margin={{ left: 8, right: 36, top: 4, bottom: 4 }}>
                    <XAxis type="number" hide />
                    <YAxis type="category" dataKey="name" width={128} axisLine={false} tickLine={false} tick={{ fill: "currentColor", fontSize: 14 }} />
                    <Bar dataKey="value" radius={[0, 6, 6, 0]} barSize={22} isAnimationActive={false}>
                      {data.map((_, i) => <Cell key={i} fill={SHADES[i]} />)}
                      <LabelList dataKey="value" position="right" style={{ fill: "currentColor", fontSize: 13 }} />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </section>
        </>
      )}
    </AdminFrame>
  );
}
