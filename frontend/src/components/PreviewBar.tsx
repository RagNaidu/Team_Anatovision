import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Eye } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/state/auth";
import { Button } from "@/components/ui/button";

export function PreviewBar() {
  const { preview, refresh } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  if (!preview) return null;
  async function exit() {
    setBusy(true); setErr(null);
    try { await api.adminPreviewExit(); await refresh(); navigate("/admin"); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }
  return (
    <div role="region" aria-label="Preview" className="flex min-h-10 flex-wrap items-center justify-center gap-x-3 gap-y-1 border-b border-line-strong bg-warn-soft px-4 py-1.5 text-[13px] text-warn">
      <Eye size={14} strokeWidth={1.5} aria-hidden />
      <span>Previewing as a student. Nothing is saved.</span>
      <span className="text-muted">({preview.profile === "full" ? "Full access" : preview.name})</span>
      {err && <span role="alert" className="text-accent">{err}</span>}
      <Button size="sm" variant="outline" onClick={() => void exit()} disabled={busy} className="h-7">Exit preview</Button>
    </div>
  );
}
