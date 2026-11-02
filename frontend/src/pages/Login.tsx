import { useState, type FormEvent } from "react";
import { Navigate } from "react-router-dom";
import { Eye, EyeOff } from "lucide-react";
import { Wordmark } from "@/components/Wordmark";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/state/auth";
import { errorMessage } from "@/lib/api";

export default function Login() {
  const { status, user, preview, signIn, notice } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (status === "in" && user) return <Navigate to={user.role === "instructor" && !preview ? "/admin" : "/ask"} replace />;

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password) { setError("Enter your username and password."); return; }
    setBusy(true); setError(null);
    try { await signIn(username.trim(), password); } catch (err) { setError(errorMessage(err, "Couldn't sign in. Please try again.")); } finally { setBusy(false); }
  }

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-bone px-4 py-10">
      <div className="w-full max-w-[400px] rounded-xl border border-line bg-surface p-8 shadow-soft">
        <h1 className="m-0"><Wordmark size={34} /></h1>
        <p className="mt-1 font-serif text-[15px] italic text-muted">Anatomy lab assistant</p>
        <form onSubmit={submit} className="mt-8 space-y-4" noValidate>
          <div>
            <label htmlFor="username" className="mb-1 block text-[14px] text-body-2">Username</label>
            <input id="username" name="username" autoComplete="username" autoFocus value={username} onChange={(e) => setUsername(e.target.value)}
              className="h-11 w-full rounded-lg border border-line-strong bg-bone px-3 text-[15px]" />
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-[14px] text-body-2">Password</label>
            <div className="relative">
              <input id="password" name="password" type={show ? "text" : "password"} autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)}
                className="h-11 w-full rounded-lg border border-line-strong bg-bone py-0 pl-3 pr-11 text-[15px]" />
              <button type="button" onClick={() => setShow((v) => !v)} aria-label={show ? "Hide password" : "Show password"} aria-pressed={show}
                className="absolute right-1.5 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md text-muted transition-colors duration-150 hover:bg-surface-2 hover:text-ink">
                {show ? <EyeOff size={17} strokeWidth={1.5} aria-hidden /> : <Eye size={17} strokeWidth={1.5} aria-hidden />}
              </button>
            </div>
          </div>
          <div aria-live="polite" className="min-h-[20px] text-[14px]">
            {error ? <p role="alert" className="text-accent">{error}</p> : notice ? <p className="text-muted">{notice}</p> : null}
          </div>
          <Button type="submit" size="lg" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
        </form>
      </div>
      <p className="mt-6 text-center text-[13px] text-muted">For students and instructors of the Human Anatomy Lab.</p>
    </div>
  );
}
