import { useState } from "react";
import { api, errorMessage } from "@/lib/api";
import { FLAG_REASONS } from "@/lib/types";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export function FlagDialog({ messageId, open, onOpenChange }: { messageId: string; open: boolean; onOpenChange: (o: boolean) => void }) {
  const [reason, setReason] = useState<string>(FLAG_REASONS[0]);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function submit() {
    setBusy(true); setErr(null);
    try {
      await api.flagMessage(messageId, reason, comment.trim() || undefined);
      setSent(true);
    } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }
  function change(o: boolean) {
    onOpenChange(o);
    if (!o) setTimeout(() => { setSent(false); setComment(""); setErr(null); setReason(FLAG_REASONS[0]); }, 200);
  }
  return (
    <Dialog open={open} onOpenChange={change}>
      <DialogContent title={sent ? "Thank you" : "Report an error"} description={sent ? undefined : "This goes to your instructor, who decides what is correct."}>
        {sent ? (
          <>
            <p className="text-[14px] text-body-2">Your report was sent to Dr. Inglis.</p>
            <div className="mt-4 flex justify-end"><DialogClose asChild><Button>Close</Button></DialogClose></div>
          </>
        ) : (
          <form onSubmit={(e) => { e.preventDefault(); void submit(); }}>
            <fieldset className="space-y-1.5">
              <legend className="sr-only">Reason</legend>
              {FLAG_REASONS.map((r) => (
                <label key={r} className="flex cursor-pointer items-center gap-2.5 rounded-md px-1 py-1 text-[14px] hover:bg-surface-2">
                  <input type="radio" name="reason" value={r} checked={reason === r} onChange={() => setReason(r)} className="h-4 w-4 accent-[#8A2D2A]" />
                  {r}
                </label>
              ))}
            </fieldset>
            <label htmlFor="flag-comment" className="mt-3 block text-[13px] text-muted">Anything to add? (optional)</label>
            <textarea id="flag-comment" value={comment} onChange={(e) => setComment(e.target.value)} maxLength={500} rows={3}
              className="mt-1 w-full resize-none rounded-md border border-line-strong bg-bone p-2.5 text-[14px]" />
            {err && <p role="alert" className="mt-2 text-[13px] text-accent">{err}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
              <Button type="submit" disabled={busy}>Send report</Button>
            </div>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
