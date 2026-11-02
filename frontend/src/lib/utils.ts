import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";
import type { ChatSummary } from "./types";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** localStorage that never throws (private windows, blocked storage). */
export const store = {
  get<T>(key: string, fallback: T): T {
    try {
      const v = localStorage.getItem(key);
      return v === null ? fallback : (JSON.parse(v) as T);
    } catch { return fallback; }
  },
  set(key: string, value: unknown) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* ignore */ }
  },
  remove(key: string) {
    try { localStorage.removeItem(key); } catch { /* ignore */ }
  },
};

export function initials(name: string): string {
  const parts = name.replace(/^(dr|prof)\.?\s+/i, "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return ((parts[0][0] ?? "") + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();

export type ChatGroupLabel = "Today" | "Yesterday" | "Previous 7 days" | "Older";
export function groupChats(chats: ChatSummary[], now = new Date()): { label: ChatGroupLabel; chats: ChatSummary[] }[] {
  const today = startOfDay(now);
  const day = 86_400_000;
  const groups: Record<ChatGroupLabel, ChatSummary[]> = { Today: [], Yesterday: [], "Previous 7 days": [], Older: [] };
  for (const c of [...chats].sort((a, b) => b.updated_at.localeCompare(a.updated_at))) {
    const t = startOfDay(new Date(c.updated_at));
    const diff = Math.round((today - t) / day);
    if (diff <= 0) groups.Today.push(c);
    else if (diff === 1) groups.Yesterday.push(c);
    else if (diff <= 7) groups["Previous 7 days"].push(c);
    else groups.Older.push(c);
  }
  return (Object.keys(groups) as ChatGroupLabel[]).filter((k) => groups[k].length).map((label) => ({ label, chats: groups[label] }));
}

export function formatDate(iso: string, opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" }): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-US", opts);
}
export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function roman(n: number): string {
  const map: [number, string][] = [[10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]];
  let out = "";
  let x = n;
  for (const [v, s] of map) while (x >= v) { out += s; x -= v; }
  return out || String(n);
}

export function seconds(ms: number): string {
  const s = ms / 1000;
  return s < 10 ? `${s.toFixed(s < 1 ? 1 : 0)} s` : `${Math.round(s)} s`;
}

/** "Lecture 08 - Anterior and Medial Thigh" -> "Lecture 08" */
export function shortLecture(title: string): string {
  const m = title.match(/^(Lecture\s+\d+\w*|ANA\d+\s+Class\s+\d+)/i);
  return m ? m[1] : title;
}

export const BODY_LEVELS = {
  fat: ["more", "average", "less"],
  muscle: ["more", "average", "less"],
  build: ["large", "average", "small"],
} as const;
export interface BodyType { fat: string; muscle: string; build: string }
export function bodyTypeString(b: BodyType): string {
  return `${b.fat} fat, ${b.muscle} muscle, ${b.build} build`;
}
