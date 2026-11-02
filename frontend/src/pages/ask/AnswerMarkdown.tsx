import { useMemo } from "react";
import ReactMarkdown, { defaultUrlTransform, type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { motion } from "framer-motion";
import { linkCitations, splitBlocks } from "@/lib/citations";
import { CitationChip } from "./CitationChip";
import type { Source } from "@/lib/types";

const urlTransform = (url: string) => (url.startsWith("cite:") ? url : defaultUrlTransform(url));

/** Markdown with [n] markers turned into citation chips. `reveal` shows a fresh answer block by block. */
export function AnswerMarkdown({
  markdown, sources, activeN, onCite, reveal,
}: { markdown: string; sources: Source[]; activeN?: number | null; onCite?: (n: number) => void; reveal?: boolean }) {
  const blocks = useMemo(() => splitBlocks(linkCitations(markdown, sources)), [markdown, sources]);
  const components: Components = useMemo(() => ({
    a({ href, children }) {
      if (href?.startsWith("cite:")) {
        const n = Number(href.slice(5));
        return <CitationChip n={n} active={activeN === n} onClick={() => onCite?.(n)} />;
      }
      return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
    },
  }), [activeN, onCite]);

  return (
    <div className="prose-answer">
      {blocks.map((b, i) => (
        <motion.div key={i} initial={reveal ? { opacity: 0, y: 6 } : false} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.28, ease: "easeOut", delay: reveal ? i * 0.12 : 0 }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]} urlTransform={urlTransform} components={components}>{b}</ReactMarkdown>
        </motion.div>
      ))}
    </div>
  );
}
