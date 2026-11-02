import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, errorMessage } from "@/lib/api";
import type { ChatSummary, GuideHistoryItem, QuizHistoryItem, Scope } from "@/lib/types";
import { useAuth } from "./auth";

interface DataValue {
  scope: Scope | null;
  scopeError: string | null;
  chats: ChatSummary[];
  chatsLoading: boolean;
  chatsError: string | null;
  refreshChats: () => Promise<void>;
  renameChat: (id: string, title: string) => Promise<void>;
  removeChat: (id: string) => Promise<void>;
  quizHistory: QuizHistoryItem[] | null;
  quizHistoryError: string | null;
  refreshQuizHistory: () => Promise<void>;
  removeQuiz: (id: string) => Promise<void>;
  guideHistory: GuideHistoryItem[] | null;
  guideHistoryError: string | null;
  refreshGuideHistory: () => Promise<void>;
  removeGuideHistory: (id: string) => Promise<void>;
}
const Ctx = createContext<DataValue | null>(null);

/** Scope and chat list, shared by the sidebar and the pages. Instructors outside a preview only read the scope. */
export function DataProvider({ children }: { children: ReactNode }) {
  const { user, preview } = useAuth();
  const studentTools = user?.role === "student" || Boolean(preview);
  const [scope, setScope] = useState<Scope | null>(null);
  const [scopeError, setScopeError] = useState<string | null>(null);
  const [chats, setChats] = useState<ChatSummary[]>([]);
  const [chatsLoading, setChatsLoading] = useState(false);
  const [chatsError, setChatsError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    let live = true;
    setScope(null);
    api.scope().then((s) => live && (setScope(s), setScopeError(null))).catch((e) => live && setScopeError(errorMessage(e)));
    return () => { live = false; };
  }, [user, preview]);

  const refreshChats = useCallback(async () => {
    if (!studentTools) { setChats([]); return; }
    setChatsLoading(true);
    try { setChats(await api.listChats()); setChatsError(null); } catch (e) { setChatsError(errorMessage(e)); } finally { setChatsLoading(false); }
  }, [studentTools]);
  useEffect(() => { void refreshChats(); }, [refreshChats, preview]);

  const renameChat = useCallback(async (id: string, title: string) => {
    const r = await api.renameChat(id, title);
    setChats((cs) => cs.map((c) => (c.id === id ? { ...c, title: r.title } : c)));
  }, []);
  const removeChat = useCallback(async (id: string) => {
    await api.deleteChat(id);
    setChats((cs) => cs.filter((c) => c.id !== id));
  }, []);

  const [quizHistory, setQuizHistory] = useState<QuizHistoryItem[] | null>(null);
  const [quizHistoryError, setQuizHistoryError] = useState<string | null>(null);
  const [guideHistory, setGuideHistory] = useState<GuideHistoryItem[] | null>(null);
  const [guideHistoryError, setGuideHistoryError] = useState<string | null>(null);
  // histories belong to one student: forget them when the user or the preview changes
  useEffect(() => { setQuizHistory(null); setGuideHistory(null); }, [user, preview]);

  const refreshQuizHistory = useCallback(async () => {
    if (!studentTools) return;
    try { setQuizHistory(await api.quizHistory()); setQuizHistoryError(null); } catch (e) { setQuizHistoryError(errorMessage(e)); }
  }, [studentTools]);
  const removeQuiz = useCallback(async (id: string) => {
    await api.deleteQuizHistory(id);
    setQuizHistory((h) => h?.filter((q) => q.id !== id) ?? null);
  }, []);
  const refreshGuideHistory = useCallback(async () => {
    if (!studentTools) return;
    try { setGuideHistory(await api.guideHistory()); setGuideHistoryError(null); } catch (e) { setGuideHistoryError(errorMessage(e)); }
  }, [studentTools]);
  const removeGuideHistory = useCallback(async (id: string) => {
    await api.deleteGuideHistory(id);
    setGuideHistory((h) => h?.filter((g) => g.id !== id) ?? null);
  }, []);

  const value = useMemo(() => ({
    scope, scopeError, chats, chatsLoading, chatsError, refreshChats, renameChat, removeChat,
    quizHistory, quizHistoryError, refreshQuizHistory, removeQuiz, guideHistory, guideHistoryError, refreshGuideHistory, removeGuideHistory,
  }), [scope, scopeError, chats, chatsLoading, chatsError, refreshChats, renameChat, removeChat, quizHistory, quizHistoryError, refreshQuizHistory, removeQuiz,
    guideHistory, guideHistoryError, refreshGuideHistory, removeGuideHistory]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
export function useData(): DataValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useData outside DataProvider");
  return v;
}
