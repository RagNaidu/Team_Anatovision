import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { Plus, LogOut, Sun, Moon, Monitor } from "lucide-react";
import { Wordmark } from "./Wordmark";
import { ChatList } from "./ChatList";
import { GuideHistory, QuizHistory } from "./SidebarHistories";
import { useAuth } from "@/state/auth";
import { cn, initials, store } from "@/lib/utils";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/dropdown";
import { useTheme } from "@/hooks/useTheme";

export interface LastGuide { kind: "guide" | "lecture"; id: string; title: string; index: number; count: number }
export const LAST_GUIDE_KEY = "av_last_guide";

const tabClass = (active: boolean) =>
  cn("relative -mb-px px-0.5 pb-2 text-[15px] transition-colors duration-150", active ? "text-side-ink" : "text-side-muted hover:text-side-ink");

export function Sidebar({ slotRef }: { slotRef: (el: HTMLElement | null) => void }) {
  const { user, preview, signOut } = useAuth();
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const instructorShell = user?.role === "instructor" && !preview;
  const mode = pathname.startsWith("/guide") ? "guide" : pathname.startsWith("/quiz") ? "quiz" : "ask";
  const { theme, setTheme } = useTheme();
  const nextTheme = theme === "system" ? "light" : theme === "light" ? "dark" : "system";
  const ThemeIcon = theme === "system" ? Monitor : theme === "light" ? Sun : Moon;

  const [last, setLast] = useState<LastGuide | null>(() => store.get<LastGuide | null>(LAST_GUIDE_KEY, null));
  useEffect(() => { setLast(store.get<LastGuide | null>(LAST_GUIDE_KEY, null)); }, [pathname]);
  const inGuideStation = /^\/guide\/[^/]+/.test(pathname);

  return (
    <div className="on-dark flex h-full flex-col border-r border-side-edge bg-side text-side-ink">
      <div className="px-5 pb-4 pt-6">
        <Link to={instructorShell ? "/admin" : "/ask"} className="block rounded-md">
          <Wordmark onDark size={26} />
        </Link>
        <p className="mt-1 font-serif text-[13px] italic text-side-muted">Anatomy lab assistant</p>
      </div>

      {instructorShell ? (
        <nav aria-label="Instructor" className="px-3">
          {[
            ["/admin", "Overview", true], ["/admin/review", "Review queue", false], ["/admin/questions", "Questions", false], ["/admin/web-quizzes", "Web quizzes", false],
            ["/admin/access", "Access", false], ["/admin/preview", "Preview as student", false],
          ].map(([to, label, end]) => (
            <NavLink key={String(to)} to={String(to)} end={Boolean(end)}
              className={({ isActive }) => cn("flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[15px] transition-colors duration-150 hover:bg-side-hover", isActive ? "text-side-ink" : "text-side-muted")}>
              {({ isActive }) => (<><span className={cn("h-1.5 w-1.5 rounded-full", isActive ? "bg-side-accent" : "bg-transparent")} aria-hidden />{label}</>)}
            </NavLink>
          ))}
        </nav>
      ) : (
        <>
          <nav aria-label="Mode" className="mx-5 flex gap-5 border-b border-side-line">
            {([["ask", "/ask", "Ask"], ["guide", "/guide", "Guide"], ["quiz", "/quiz", "Quiz"]] as const).map(([k, to, label]) => (
              <NavLink key={k} to={to} aria-current={mode === k ? "page" : undefined} className={tabClass(mode === k)}>
                {label}
                {mode === k && <span className="absolute inset-x-0 bottom-0 h-[2px] rounded-full bg-side-accent" />}
              </NavLink>
            ))}
          </nav>
          <div className="px-4 pb-3 pt-4">
            <button type="button" onClick={() => navigate("/ask", { state: { fresh: Date.now() } })}
              className="flex h-11 w-full items-center justify-center gap-2 rounded-full bg-side-ink text-[15px] font-medium text-[#1E1A17] shadow-float transition-colors duration-150 hover:bg-white">
              <Plus size={16} strokeWidth={2} className="text-[#8A2D2A]" aria-hidden /> New chat
            </button>
          </div>
          {mode === "ask" ? <ChatList /> : mode === "quiz" ? <QuizHistory /> : (
            <div className="scroll-side flex min-h-0 flex-1 flex-col overflow-y-auto">
              <GuideHistory collapsible={inGuideStation} />
              <div ref={slotRef} />
            </div>
          )}
        </>
      )}
      {instructorShell && <div className="flex-1" />}

      {!instructorShell && last && !inGuideStation && (
        <Link to={last.kind === "lecture" ? `/guide/lecture/${last.id}/${last.index}` : `/guide/${last.id}/${last.index}`}
          className="mx-4 mb-3 block rounded-lg border border-side-line bg-side-hover px-3.5 py-3 transition-colors duration-150 hover:border-side-faint">
          <span className="font-serif text-[13px] italic text-side-accent">Continue guide →</span>
          <span className="mt-0.5 block truncate text-[14px] text-side-ink">{last.title}</span>
          <span className="mt-2 flex gap-[3px]" aria-label={`Station ${last.index + 1} of ${last.count}`}>
            {Array.from({ length: Math.min(last.count, 12) }).map((_, i) => (
              <span key={i} className={cn("h-1.5 flex-1 rounded-full", i <= last.index ? "bg-side-accent" : "bg-[#4F453D]")} />
            ))}
          </span>
        </Link>
      )}

      <div className="border-t border-side-line p-3">
        <Menu>
          <MenuTrigger className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left transition-colors duration-150 hover:bg-side-hover data-[state=open]:bg-side-hover">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-side-ink text-[12px] font-semibold text-[#1E1A17]" aria-hidden>{initials(user?.name ?? "")}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[14px] text-side-ink">{user?.name}</span>
              <span className="block text-[12px] text-side-muted">{user?.role === "instructor" ? "Instructor" : "Student"}</span>
            </span>
          </MenuTrigger>
          <MenuContent side="top" align="start" className="w-56">
            <MenuItem onSelect={(e) => { e.preventDefault(); setTheme(nextTheme); }}><ThemeIcon size={14} strokeWidth={1.5} /> Appearance: {theme === "system" ? "System" : theme === "light" ? "Light" : "Dark"}</MenuItem>
            <MenuItem onSelect={() => void signOut()}><LogOut size={14} strokeWidth={1.5} /> Sign out</MenuItem>
          </MenuContent>
        </Menu>
      </div>
    </div>
  );
}
