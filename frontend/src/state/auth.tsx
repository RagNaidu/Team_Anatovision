import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { Preview, User } from "@/lib/types";

interface AuthValue {
  status: "loading" | "in" | "out";
  user: User | null;
  preview: Preview | null;
  notice: string | null;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  refresh: () => Promise<void>;
  clearNotice: () => void;
}
const Ctx = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<AuthValue["status"]>("loading");
  const [user, setUser] = useState<User | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const me = await api.me();
      setUser(me.user);
      setPreview(me.preview ?? null);
      setStatus("in");
    } catch {
      setUser(null);
      setPreview(null);
      setStatus("out");
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const on = () => {
      setUser(null);
      setPreview(null);
      setStatus("out");
      setNotice("Your session ended. Please sign in again.");
    };
    window.addEventListener("av:unauthorized", on);
    return () => window.removeEventListener("av:unauthorized", on);
  }, []);

  const signIn = useCallback(async (username: string, password: string) => {
    const r = await api.login(username, password);
    setNotice(null);
    setUser(r.user);
    setPreview(null);
    setStatus("in");
    // /auth/me is the source of truth for preview (it is always null right after a login)
  }, []);
  const signOut = useCallback(async () => {
    try { await api.logout(); } catch { /* the cookie may already be gone */ }
    setUser(null);
    setPreview(null);
    setStatus("out");
  }, []);

  const value = useMemo<AuthValue>(() => ({ status, user, preview, notice, signIn, signOut, refresh, clearNotice: () => setNotice(null) }), [status, user, preview, notice, signIn, signOut, refresh]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
export function useAuth(): AuthValue {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth outside AuthProvider");
  return v;
}
