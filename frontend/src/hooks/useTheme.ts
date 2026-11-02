import { useCallback, useEffect, useState } from "react";
import { store } from "@/lib/utils";

export type ThemeChoice = "system" | "light" | "dark";
export function applyTheme(t: ThemeChoice) {
  const root = document.documentElement;
  if (t === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", t);
}
export function useTheme() {
  const [theme, setTheme] = useState<ThemeChoice>(() => store.get<ThemeChoice>("av_theme", "system"));
  useEffect(() => { applyTheme(theme); }, [theme]);
  const set = useCallback((t: ThemeChoice) => { store.set("av_theme", t); setTheme(t); }, []);
  return { theme, setTheme: set };
}
