import { unified } from "unified";
import remarkParse from "remark-parse";
import remarkGfm from "remark-gfm";
import type { Source } from "./types";

/** Stray punctuation just before a marker ("artery,. [1]", "it. . [1]", "artery, [1]") is cleaned: a run of commas, colons, semicolons, dots and spaces becomes one full stop
 *  if it contained a dot (three or more dots stay an ellipsis), otherwise nothing. */
export function tidyBeforeMarkers(text: string): string {
  return text.replace(/([^\s,;:.])[ \t]*([,;:.][,;:. \t]*)(?=\[\d{1,3}\](?!\())/g, (_m, c: string, run: string) => {
    const dots = (run.match(/\./g) ?? []).length;
    return c + (dots >= 3 ? "..." : dots ? "." : "") + " ";
  });
}

/** Turn "[1]" markers that have a Source into links "[1](cite:1)". A marker without a Source is dropped, never printed. Code is left alone. */
export function linkCitations(md: string, sources: Pick<Source, "n">[]): string {
  const valid = new Set(sources.map((s) => s.n));
  return md
    .split(/(```[\s\S]*?```)/g)
    .map((part, i) => {
      if (i % 2 === 1) return part;
      return tidyBeforeMarkers(part).replace(/[ \t]?\[(\d{1,3})\](?!\()/g, (m, n: string) => (valid.has(Number(n)) ? `${m.startsWith("[") ? "" : m[0]}[${n}](cite:${n})` : ""));
    })
    .join("");
}

/** Split markdown into its top-level blocks (a list stays one block), so a fresh answer can appear paragraph by paragraph. */
export function splitBlocks(md: string): string[] {
  const tree = unified().use(remarkParse).use(remarkGfm).parse(md);
  const blocks: string[] = [];
  for (const node of tree.children) {
    const s = node.position?.start.offset;
    const e = node.position?.end.offset;
    if (s === undefined || e === undefined) continue;
    blocks.push(md.slice(s, e));
  }
  return blocks.length ? blocks : [md];
}

const LABELS: Record<string, string> = {
  notes: "Lecture notes", guide: "Dissection guide", openstax: "OpenStax", wikipedia: "Wikipedia", web: "Web", verified_fix: "Verified correction",
};
export const typeLabel = (t: string) => ({ notes: "Course notes", guide: "Dissection guide", openstax: "OpenStax", wikipedia: "Wikipedia", web: "Web", verified_fix: "Verified fix" }[t] ?? t);

/** "1 · Lecture notes · L08", "2 · OpenStax 11.6" */
export function pillLabel(s: Source): string {
  switch (s.type) {
    case "notes": {
      const m = s.subtitle.match(/Lecture\s+(\d+\w*)/i);
      return m ? `${LABELS.notes} · L${m[1]}` : LABELS.notes;
    }
    case "guide":
      return `${LABELS.guide} · ${s.subtitle}`;
    case "openstax": {
      const m = s.title.match(/section\s+([\d.]+)/i);
      return m ? `OpenStax ${m[1]}` : "OpenStax";
    }
    case "wikipedia":
      return "Wikipedia";
    case "web": {
      try { return new URL(s.url ?? "").hostname.replace(/^www\./, ""); } catch { return "Web"; }
    }
    default:
      return LABELS[s.type] ?? s.title;
  }
}
