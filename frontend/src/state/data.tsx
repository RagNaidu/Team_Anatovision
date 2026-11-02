import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api, errorMessage } from "@/lib/api";
import type { ChatSummary, Scope } from "@/lib/types";
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

  const value = useMemo(() => ({ scope, scopeError, chats, chatsLoading, chatsError, refreshChats, renameChat, removeChat }), [scope, scopeError, chats, chatsLoading, chatsError, refreshChats, renameChat, removeChat]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
export function useData(): DataValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useData outside DataProvider");
  return v;
}
