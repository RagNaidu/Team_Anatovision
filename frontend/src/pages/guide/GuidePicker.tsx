import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { GuideSummary } from "@/lib/types";
import { useData } from "@/state/data";
import { Notice, PageTitle, Segmented, Skeleton } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const REGION_ORDER = ["Back", "Upper limb", "Lower limb", "Thorax", "Abdomen", "Thorax and abdomen", "Head and neck", "Other"];

function Card({ to, kicker, title, meta, locked }: { to: string; kicker: string; title: string; meta: string; locked: boolean }) {
  const body = (
    <>
      <span className="serif-label block">{kicker}</span>
      <span className="mt-0.5 block font-serif text-[18px] font-semibold leading-snug text-ink">{title}</span>
      <span className="mt-2 flex items-center gap-1.5 text-[13px] text-muted">
        {locked ? <><Lock size={13} strokeWidth={1.5} aria-hidden /> Ask your instructor</> : meta}
      </span>
    </>
  );
  return locked ? (
    <div aria-disabled="true" className="rounded-xl border border-line bg-surface p-4 opacity-55">{body}</div>
  ) : (
    <Link to={to} className="block rounded-xl border border-line bg-surface p-4 transition-colors duration-150 hover:border-line-strong hover:bg-surface-2">{body}</Link>
  );
}

export default function GuidePicker() {
  const { scope, scopeError } = useData();
  const [tab, setTab] = useState<"guides" | "lectures">("guides");
  const [guides, setGuides] = useState<GuideSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);

  useEffect(() => {
    let live = true;
    setError(null); setGuides(null);
    api.listGuides().then((g) => live && setGuides(g)).catch((e) => live && setError(errorMessage(e)));
    return () => { live = false; };
  }, [tries]);

  const regions = REGION_ORDER.map((r) => ({ region: r, items: (guides ?? []).filter((g) => (REGION_ORDER.includes(g.region) ? g.region : "Other") === r).sort((a, b) => a.class_number - b.class_number) })).filter((r) => r.items.length);

  return (
    <div className="min-h-full">
      <div className="mx-auto w-full max-w-[960px] px-6 py-8 max-lg:px-4">
        <PageTitle sub="Pick a dissection guide to work through, station by station.">Guide</PageTitle>
        <Segmented<"guides" | "lectures"> label="Source" value={tab} onChange={setTab}
          options={[{ value: "guides", label: "Dissection guides" }, { value: "lectures", label: "Lecture notes (sample)" }]} />

        {tab === "guides" ? (
          error ? (
            <Notice tone="error" className="mt-6" action={<Button size="sm" variant="outline" onClick={() => setTries((t) => t + 1)}>Try again</Button>}>{error}</Notice>
          ) : !guides ? (
            <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-label="Loading guides">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-24 !rounded-xl" />)}</div>
          ) : guides.length === 0 ? (
            <Notice className="mt-6">No dissection guides are available yet.</Notice>
          ) : (
            regions.map((r) => (
              <section key={r.region} className="mt-8">
                <h2 className="serif-label mb-3 !text-[15px]">{r.region}</h2>
                <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                  {r.items.map((g) => (
                    <li key={g.id}>
                      <Card to={`/guide/${g.id}`} kicker={`Class ${g.class_number}`} title={g.title} locked={!g.granted} meta={`${g.station_count} station${g.station_count === 1 ? "" : "s"}`} />
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )
        ) : (
          <div className="mt-6">
            <p className={cn("mb-4 text-[14px] text-muted")}>Sample mode: built from the lecture's own order, not a dissection procedure.</p>
            {scopeError ? <Notice tone="error">{scopeError}</Notice> : !scope ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-24 !rounded-xl" />)}</div>
            ) : (
              <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {scope.lectures.map((l) => {
                  const [kicker, ...rest] = l.title.split(/\s+-\s+/);
                  return <li key={l.id}><Card to={`/guide/lecture/${l.id}`} kicker={kicker} title={rest.join(" - ") || l.title} locked={!l.granted} meta="Read-only walk-through" /></li>;
                })}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
