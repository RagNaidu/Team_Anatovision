import { useCallback, useEffect, useRef, useState } from "react";

/** Keeps a scroll container pinned to the bottom while content grows, unless the reader scrolled up. */
export function useStickToBottom() {
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const stuck = useRef(true);
  const [atBottom, setAtBottom] = useState(true);

  const toBottom = useCallback((smooth = true) => {
    const el = scrollRef.current;
    if (!el) return;
    stuck.current = true;
    setAtBottom(true);
    el.scrollTo({ top: el.scrollHeight, behavior: smooth && !window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "smooth" : "auto" });
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const onScroll = () => {
      const near = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      stuck.current = near;
      setAtBottom(near);
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    const content = contentRef.current;
    const el = scrollRef.current;
    if (!content || !el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => {
      if (stuck.current) el.scrollTop = el.scrollHeight;
      else setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
    });
    ro.observe(content);
    return () => ro.disconnect();
  }, []);

  return { scrollRef, contentRef, atBottom, toBottom };
}
