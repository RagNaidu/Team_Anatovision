import { useEffect, useState } from "react";

export function useMediaQuery(query: string): boolean {
  const get = () => (typeof window !== "undefined" && window.matchMedia ? window.matchMedia(query).matches : false);
  const [matches, setMatches] = useState(get);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const on = () => setMatches(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, [query]);
  return matches;
}
export const useIsDesktop = () => useMediaQuery("(min-width: 1024px)"); // sidebar is persistent
export const useIsWide = () => useMediaQuery("(min-width: 1280px)"); // source panel is a column
export const useIsPhone = () => useMediaQuery("(max-width: 639px)"); // bottom sheet
export const useReducedMotion = () => useMediaQuery("(prefers-reduced-motion: reduce)");
