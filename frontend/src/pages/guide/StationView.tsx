import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowLeft, ArrowRight, ImageIcon } from "lucide-react";
import { api, ApiError, errorMessage, imageSrc } from "@/lib/api";
import type { BodyTip, Explanation, GuideBodyType, GuideSummary, Station, StationCheck, Verdict } from "@/lib/types";
import { bodyAdapts, bodyLabel } from "@/lib/bodyType";
import { BodyTypeAsk, BodyTypeChip } from "@/components/BodyTypeChoice";
import { useData } from "@/state/data";
import { SidebarPortal } from "@/components/SidebarSlot";
import { SpineBar } from "@/components/Vertebrae";
import { ProgressRow } from "@/components/ProgressRow";
import { Button } from "@/components/ui/button";
import { Notice, Skeleton } from "@/components/ui/misc";
import { cn, roman, store } from "@/lib/utils";
import { LAST_GUIDE_KEY, type LastGuide } from "@/components/Sidebar";
import { AnswerMarkdown } from "@/pages/ask/AnswerMarkdown";
import { SourcePanelHost } from "@/pages/ask/SourcePanel";
import { MarkedImage } from "@/components/guide/MarkedImage";
import { DISCLAIMER, Lightbox } from "@/components/guide/Lightbox";
import { DescribeBox } from "./DescribeBox";

const VERDICT: Record<Verdict, { label: string; cls: string }> = {
  correct: { label: "Correct", cls: "bg-ok-soft text-ok" },
  partly: { label: "Partly", cls: "bg-warn-soft text-warn" },
  not_matching: { label: "Not matching", cls: "bg-accent-soft text-accent-soft-ink" },
};
export function VerdictPill({ verdict }: { verdict: string }) {
  // an unknown verdict from a newer backend still gets a calm neutral pill with its own text
  const v = VERDICT[verdict as Verdict] ?? { label: String(verdict).replace(/_/g, " ") || "Checked", cls: "bg-surface-2 text-body-2" };
  return <span className={cn("inline-flex h-7 items-center rounded-full px-3 text-[13px] font-medium", v.cls)}>{v.label}</span>;
}

type CheckState = { text: string; phase: "idle" | "loading" | "done" | "error"; result?: StationCheck; error?: string };
const PROGRESS_KEY = "av_guide_progress";

export default function StationView({ kind }: { kind: "guide" | "lecture" }) {
  const { id = "", index: indexParam } = useParams();
  const navigate = useNavigate();
  const { scope, refreshGuideHistory } = useData();
  const [stations, setStations] = useState<Station[] | null>(null);
  const [guide, setGuide] = useState<GuideSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tries, setTries] = useState(0);
  const [checks, setChecks] = useState<Record<number, CheckState>>({});
  const [panel, setPanel] = useState<number | null>(null);
  const [furthest, setFurthest] = useState(0);
  const sizeRef = useRef(0);
  // the cadaver's body type for THIS guide: undefined = not known yet, null = not chosen (ask first)
  const [bodyType, setBodyType] = useState<GuideBodyType | null | undefined>(undefined);
  const [tip, setTip] = useState<BodyTip | null>(null);
  const [notice, setNotice] = useState<string | null>(null);        // set once when a revised guide moved or reset the place

  const [stepSel, setStepSel] = useState(0);                      // the selected step of the station (only used when the station has approved marks)
  const [imgIdx, setImgIdx] = useState(0);
  const [lightbox, setLightbox] = useState(false);
  const [explain, setExplain] = useState<{ phase: "idle" | "loading" | "done" | "error"; data?: Explanation; error?: string }>({ phase: "idle" });

  const key = `${kind}:${id}`;
  const btKey = `av_guide_bt:${id}`;
  const index = Math.max(0, Number.parseInt(indexParam ?? "0", 10) || 0);

  useEffect(() => {
    let live = true;
    setStations(null); setError(null); setChecks({}); setPanel(null);
    const load = kind === "guide" ? api.guideStations(id) : api.lectureStations(id);
    load.then((s) => {
      if (!live) return;
      setStations(s);
      sizeRef.current = s.length;
      setFurthest(store.get<Record<string, number>>(PROGRESS_KEY, {})[key] ?? 0);
    }).catch((e) => live && setError(errorMessage(e)));
    if (kind === "guide") api.listGuides().then((g) => live && setGuide(g.find((x) => x.id === id) ?? null)).catch(() => undefined);
    return () => { live = false; };
  }, [id, kind, tries, key]);

  const lectureTitle = scope?.lectures.find((l) => l.id === id)?.title;
  const heading = kind === "guide" ? (guide ? `Class ${guide.class_number} · ${guide.title}` : "Dissection guide") : lectureTitle ? lectureTitle.replace(/\s+-\s+/, " · ") : "Lecture notes";
  const shortHeading = kind === "guide" && guide ? `Class ${guide.class_number} · ${guide.title}` : heading;

  const st = stations && stations[Math.min(index, stations.length - 1)];
  const cur = st ? st.index : 0;
  const count = stations?.length ?? 0;
  const images = st?.images ?? [];
  const hasMarks = images.some((i) => i.marks.length > 0) && !!st && st.steps.length > 0;
  const activeStep = hasMarks ? Math.min(stepSel, (st?.steps.length ?? 1) - 1) : null;
  useEffect(() => { setStepSel(0); setImgIdx(0); setLightbox(false); setExplain({ phase: "idle" }); }, [st?.index, id]);

  // the saved body type of this guide (the server first, then this browser); none yet = ask before the first station
  useEffect(() => {
    if (kind !== "guide") { setBodyType(null); return; }
    let live = true;
    setBodyType(undefined);
    const local = store.get<GuideBodyType | null>(btKey, null);
    api.guideHistory().then((h) => { if (!live) return; const row = h.find((x) => x.id === key); setNotice(row?.notice ?? null); setBodyType(row?.body_type ?? local); }).catch(() => live && setBodyType(local));
    return () => { live = false; };
  }, [kind, key, btKey]);

  // the note for this station and body type (a line from the guide, and labelled general tips)
  useEffect(() => {
    setTip(null);
    if (kind !== "guide" || !stations || !bodyAdapts(bodyType)) return;
    const s0 = stations[Math.min(index, stations.length - 1)];
    if (!s0 || s0.image_only) return;
    let live = true;
    api.guideBodyTip(id, s0.index, bodyType as GuideBodyType).then((t) => live && setTip(t)).catch(() => undefined);
    return () => { live = false; };
  }, [kind, id, stations, index, bodyType]);

  function chooseBodyType(v: GuideBodyType) {
    setBodyType(v);
    store.set(btKey, v);
    api.saveGuideHistory("guide", id, Math.min(index, Math.max(0, (stations?.length ?? 1) - 1)), v).then(() => refreshGuideHistory()).catch(() => undefined);
  }

  // remember where the student is (the sidebar's "Continue guide" card) and how far they got
  useEffect(() => {
    if (!stations || !st) return;
    const last: LastGuide = { kind, id, title: shortHeading, index: cur, count };
    store.set(LAST_GUIDE_KEY, last);
    const all = store.get<Record<string, number>>(PROGRESS_KEY, {});
    if ((all[key] ?? 0) < cur) { all[key] = cur; store.set(PROGRESS_KEY, all); setFurthest(cur); }
  }, [stations, st, cur, count, kind, id, key, shortHeading]);

  // the server keeps the guide and the station reached, for the sidebar's history
  useEffect(() => {
    if (!stations || !st || bodyType === undefined) return;          // wait until the saved notice and body type have been read
    let live = true;
    api.saveGuideHistory(kind, id, cur).then(() => { if (live) void refreshGuideHistory(); }).catch(() => undefined);
    return () => { live = false; };
  }, [stations, st, cur, kind, id, refreshGuideHistory, bodyType === undefined]); // eslint-disable-line react-hooks/exhaustive-deps

  const go = useCallback((i: number) => navigate(`/guide/${kind === "lecture" ? "lecture/" : ""}${id}/${i}`), [navigate, kind, id]);

  const check = checks[cur] ?? { text: "", phase: "idle" as const };
  const setCheck = (patch: Partial<CheckState>) => setChecks((c) => ({ ...c, [cur]: { ...(c[cur] ?? { text: "", phase: "idle" as const }), ...patch } }));

  async function runCheck(override?: string) {
    if (!st) return;
    const text = (override ?? check.text).trim();
    if (!text) return;
    setCheck({ phase: "loading", error: undefined });
    try {
      const r = await api.checkStation(id, st.index, text, kind === "guide" ? bodyType : null);
      setChecks((c) => ({ ...c, [st.index]: { text, phase: "done", result: r } }));
      setPanel(null);
    } catch (e) {
      const msg = e instanceof ApiError && e.status === 422 && st.image_only ? `See slide ${st.slides[0]} in your lab guide.` : errorMessage(e);
      setChecks((c) => ({ ...c, [st.index]: { text, phase: "error", error: msg } }));
    }
  }

  const sidebar = useMemo(() => stations && (
    <div className="px-4 pb-4">
      <p className="serif-label !text-side-faint mb-2 px-1">Stations</p>
      <ol className="relative">
        {stations.map((s) => {
          const isCur = s.index === cur;
          const done = s.index < furthest && !isCur;
          return (
            <li key={s.index} className="relative">
              <button type="button" onClick={() => go(s.index)} aria-current={isCur ? "step" : undefined}
                className={cn("flex w-full items-start gap-3 rounded-lg px-1.5 py-1.5 text-left transition-colors duration-150 hover:bg-side-hover", isCur && "bg-side-hover")}>
                <span className="relative mt-[3px] flex w-5 shrink-0 justify-center">
                  <span className={cn("h-3.5 w-5 rounded-[6px] border", isCur ? "border-side-accent bg-side-hover ring-2 ring-side-accent/30" : done ? "border-side-accent bg-side-accent" : "border-[#5B4F46] bg-transparent")} />
                </span>
                <span className={cn("min-w-0 text-[14px] leading-snug", isCur ? "text-side-ink" : done ? "text-side-muted" : "text-side-faint")}>
                  <span className="sr-only">{done ? "Done. " : isCur ? "Current. " : ""}</span>{s.title}
                </span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  ), [stations, cur, furthest, go]);

  const backTo = "/guide";
  const panelSources = check.result?.sources ?? [];

  return (
    <div className="flex h-full min-h-0">
      {sidebar && <SidebarPortal>{sidebar}</SidebarPortal>}
      <div className="scroll-quiet min-w-0 flex-1 overflow-y-auto">
        <div className={cn("mx-auto w-full px-6 py-6 max-lg:px-4", images.length ? "max-w-[1280px]" : "max-w-[760px]")}>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <Link to={backTo} className="inline-flex items-center gap-1.5 rounded-md text-[14px] text-body-2 hover:text-accent"><ArrowLeft size={15} strokeWidth={1.5} aria-hidden /> All guides</Link>
            <span className="text-[14px] text-muted">{heading}</span>
          </div>

          {notice && <Notice className="mt-4">{notice}</Notice>}
          {error ? (
            <Notice tone="error" className="mt-6" action={<Button size="sm" variant="outline" onClick={() => setTries((t) => t + 1)}>Try again</Button>}>{error}</Notice>
          ) : !stations ? (
            <div className="mt-8 space-y-4" aria-label="Loading stations"><Skeleton className="h-3 w-full" /><Skeleton className="h-8 w-2/3" /><Skeleton className="h-4" /><Skeleton className="h-4 w-5/6" /><Skeleton className="h-28 !rounded-xl" /></div>
          ) : !st ? (
            <Notice className="mt-6">This guide has no stations yet.</Notice>
          ) : kind === "guide" && bodyType === undefined ? (
            <div className="mt-8 space-y-4" aria-label="Loading"><Skeleton className="h-6 w-1/3" /><Skeleton className="h-28 !rounded-xl" /></div>
          ) : kind === "guide" && bodyType === null ? (
            <BodyTypeAsk onChoose={chooseBodyType} />
          ) : (
            <AnimatePresence mode="wait" initial={false}>
              <motion.div key={st.index} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
                <div className="mt-5">
                  <SpineBar count={count} current={cur} furthest={furthest} label={`Station ${cur + 1} of ${count}`} />
                  <p className="mt-2 text-[13px] text-muted">Station {cur + 1} of {count}</p>
                </div>

                <div className="mt-6 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  <p className="serif-label !text-[16px]">Station {roman(cur + 1)}</p>
                  {kind === "guide" && <BodyTypeChip value={bodyType ?? null} onChange={chooseBodyType} />}
                </div>
                <h1 className="mt-1 font-serif text-[32px] font-semibold leading-tight max-sm:text-[26px]">{st.title}</h1>

                <div className={cn("mt-5", images.length > 0 && "grid items-start gap-x-8 gap-y-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]")}>
                  <div className={cn(images.length > 0 && "max-lg:order-2")}>
                    {st.image_only && images.length === 0 ? (
                      <div className="flex items-center gap-3 rounded-xl border border-line bg-surface px-4 py-4 text-[15px]">
                        <ImageIcon size={18} strokeWidth={1.5} className="text-muted" aria-hidden />
                        See slide {st.slides[0]} in your lab guide
                      </div>
                    ) : st.image_only ? null : (
                      <ol className="space-y-3" aria-label="Steps">
                        {st.steps.map((s, i) => {
                          const on = hasMarks && i === activeStep;
                          const body = (
                            <>
                              <span className={cn("mt-[2px] flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[12px]", on ? "border-accent bg-accent text-accent-fg" : "border-line-strong text-body-2")} aria-hidden>{i + 1}</span>
                              <span className="text-[16px] leading-relaxed">{s}</span>
                            </>
                          );
                          return (
                            <li key={i}>
                              {hasMarks ? (
                                <button type="button" onClick={() => setStepSel(i)} aria-pressed={on} aria-label={`Step ${i + 1}: ${s}`}
                                  className={cn("flex w-full gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors duration-150", on ? "border-accent bg-accent-soft/50" : "border-transparent hover:bg-surface-2")}>{body}</button>
                              ) : <div className="flex gap-3">{body}</div>}
                            </li>
                          );
                        })}
                      </ol>
                    )}
                    {kind === "guide" && !st.image_only && st.steps.length > 0 && (
                      <div className="mt-4">
                        <Button variant="outline" size="sm" disabled={explain.phase === "loading"} onClick={async () => {
                          setExplain({ phase: "loading" });
                          try { setExplain({ phase: "done", data: await api.explainStation(id, st.index, bodyType ?? null) }); } catch (e) { setExplain({ phase: "error", error: errorMessage(e) }); }
                        }}>{explain.phase === "loading" ? "Explaining…" : explain.phase === "done" ? "Explain again" : "Explain simply"}</Button>
                        <div aria-live="polite">
                          {explain.phase === "error" && <p role="alert" className="mt-2 text-[14px] text-accent">{explain.error}</p>}
                          {explain.phase === "done" && explain.data && (
                            <aside className="mt-3 rounded-xl border border-line bg-surface-2 px-4 py-3.5" aria-label="AI explanation">
                              <p className="serif-label !text-[13px]">{explain.data.label}</p>
                              <p className="mt-1.5 text-[15px] leading-relaxed">{explain.data.text}</p>
                              <p className="mt-2 text-[12px] text-muted">From: {explain.data.sources.map((s) => `${s.title}, ${s.subtitle}`).join(" · ")}</p>
                            </aside>
                          )}
                        </div>
                      </div>
                    )}
                    {st.slides.length > 0 && !st.image_only && (
                      <ul className="mt-4 flex flex-wrap gap-2" aria-label="Slides">
                        {st.slides.map((n) => <li key={n} className="rounded-full border border-line-strong bg-surface px-2.5 py-0.5 text-[12px] text-body-2">Slide {n}</li>)}
                      </ul>
                    )}
                  </div>
                  {images.length > 0 && (
                    <figure className="max-lg:order-1 lg:sticky lg:top-4" aria-label="Slide image" data-image-panel>
                      <button type="button" onClick={() => setLightbox(true)} aria-label={`Enlarge ${images[Math.min(imgIdx, images.length - 1)].alt}`} className="block w-full cursor-zoom-in rounded-xl focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent">
                        <MarkedImage image={images[Math.min(imgIdx, images.length - 1)]} step={activeStep} eager={imgIdx === 0} />
                      </button>
                      <figcaption className="mt-2 text-[13px] text-muted">{images[Math.min(imgIdx, images.length - 1)].caption} · {DISCLAIMER}</figcaption>
                      {hasMarks && activeStep !== null && <p className="mt-1 text-[13px] text-body-2" aria-live="polite">Showing the marks for step {activeStep + 1} of {st.steps.length}.</p>}
                      {images.length > 1 && (
                        <ul className="mt-3 flex gap-2 overflow-x-auto" aria-label="Slides of this station">
                          {images.map((im, k) => (
                            <li key={`${im.slide}-${im.crop ?? 1}`}>
                              <button type="button" onClick={() => setImgIdx(k)} aria-label={`Show slide ${im.slide}${(im.crop ?? 1) > 1 || images.filter((x) => x.slide === im.slide).length > 1 ? `, picture ${im.crop ?? 1}` : ""}`} aria-current={k === imgIdx} className={cn("block w-20 overflow-hidden rounded-lg border-2", k === imgIdx ? "border-accent" : "border-line")}>
                                <img src={imageSrc(im.thumb_url)} alt="" loading="lazy" className="block w-full bg-white" />
                              </button>
                            </li>
                          ))}
                        </ul>
                      )}
                      <Lightbox images={images} index={Math.min(imgIdx, images.length - 1)} onIndex={setImgIdx} open={lightbox} onClose={() => setLightbox(false)} step={activeStep} />
                    </figure>
                  )}
                </div>

                {tip && tip.lines.length > 0 && (
                  <aside aria-label={`Tip for a ${bodyLabel(bodyType).toLowerCase()} cadaver`} className="mt-5 rounded-xl border border-line bg-surface-2 px-4 py-3.5">
                    <p className="serif-label !text-[14px]">For a {bodyLabel(bodyType).toLowerCase()} cadaver</p>
                    <ul className="mt-1.5 space-y-1.5 text-[14px] leading-relaxed text-body-2">
                      {tip.lines.map((l, i) => {
                        const [label, ...rest] = l.general ? l.text.split(/:\s(.+)/s) : [null, l.text];
                        return <li key={i}>{l.general && rest.length ? <><span className="font-medium text-ink">{label}:</span> <span>{rest.join(" ")}</span></> : l.text}</li>;
                      })}
                    </ul>
                  </aside>
                )}

                {kind === "guide" && !st.image_only ? (
                  <section className="mt-8" aria-label="Check your description">
                    <DescribeBox key={st.index} text={check.text} loading={check.phase === "loading"} onCheck={(t) => void runCheck(t)}
                      onChange={(t) => setCheck({ text: t, phase: check.phase === "done" || check.phase === "error" ? "idle" : check.phase })} />
                    <div className="mt-4" aria-live="polite">
                      {check.phase === "loading" && <ProgressRow phase="waiting" label="Checking your description" />}
                      {check.phase === "error" && (
                        <Notice tone="error" action={<Button size="sm" variant="outline" onClick={() => void runCheck()}>Try again</Button>}>{check.error}</Notice>
                      )}
                      {check.phase === "done" && check.result && (
                        <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="rounded-xl border border-line bg-surface p-4">
                          <VerdictPill verdict={check.result.verdict} />
                          <div className="mt-3">
                            <AnswerMarkdown markdown={check.result.feedback_markdown} sources={check.result.sources} activeN={panel} onCite={(n) => setPanel(n)} />
                          </div>
                          {check.result.sources.length > 0 && (
                            <p className="mt-3 text-[13px] text-muted">
                              Sources: {check.result.sources.map((s, i) => (
                                <span key={s.n}>{i > 0 && ", "}<button type="button" onClick={() => setPanel(s.n)} className="underline underline-offset-2 hover:text-ink">{s.title}, {s.subtitle}</button></span>
                              ))}
                            </p>
                          )}
                        </motion.div>
                      )}
                    </div>
                  </section>
                ) : kind === "lecture" ? (
                  <p className="mt-8 text-[14px] text-muted">Sample mode: this is read-only. It follows the lecture's own order, not a dissection procedure.</p>
                ) : null}

                <div className="mt-10 flex items-center justify-between border-t border-line pt-5">
                  <Button variant="outline" onClick={() => (hasMarks && (activeStep ?? 0) > 0 ? setStepSel((activeStep ?? 0) - 1) : go(cur - 1))} disabled={cur === 0 && (!hasMarks || (activeStep ?? 0) === 0)}><ArrowLeft size={15} strokeWidth={1.5} /> {hasMarks && (activeStep ?? 0) > 0 ? "Back a step" : "Back"}</Button>
                  {hasMarks && activeStep !== null && activeStep < st.steps.length - 1 ? (
                    <Button onClick={() => setStepSel(activeStep + 1)}>Next step <ArrowRight size={15} strokeWidth={1.5} /></Button>
                  ) : cur < count - 1 ? (
                    <Button onClick={() => go(cur + 1)}>Next station <ArrowRight size={15} strokeWidth={1.5} /></Button>
                  ) : (
                    <Button onClick={() => navigate(backTo)}>Finish</Button>
                  )}
                </div>
              </motion.div>
            </AnimatePresence>
          )}
        </div>
      </div>
      <SourcePanelHost open={panel !== null && panelSources.length > 0} sources={panelSources} activeN={panel ?? 0} onSelect={setPanel} onClose={() => setPanel(null)} />
    </div>
  );
}
