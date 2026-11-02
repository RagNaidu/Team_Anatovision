import type { GuideBodyType } from "./types";

export const GUIDE_BODY_OPTIONS: { value: GuideBodyType; label: string; hint: string }[] = [
  { value: "lean", label: "Lean", hint: "less body fat" },
  { value: "average", label: "Average", hint: "nothing to adjust" },
  { value: "more_fat", label: "More fat", hint: "thicker fat and fascia" },
  { value: "more_muscular", label: "More muscular", hint: "bulkier muscles" },
  { value: "not_sure", label: "Not sure", hint: "skip this for now" },
];
export const bodyLabel = (v: GuideBodyType | null | undefined) => GUIDE_BODY_OPTIONS.find((o) => o.value === v)?.label ?? "Not chosen";
/** Lean, more fat and more muscular change the guidance; average and not sure do not. */
export const bodyAdapts = (v: GuideBodyType | null | undefined) => v === "lean" || v === "more_fat" || v === "more_muscular";
