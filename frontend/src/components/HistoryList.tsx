import { useState, type ReactNode } from "react";
import { NavLink } from "react-router-dom";
import { MoreHorizontal, Trash2 } from "lucide-react";
import { errorMessage } from "@/lib/api";
import { cn, groupByDate } from "@/lib/utils";
import { Skeleton } from "@/components/ui/misc";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/dropdown";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export interface HistoryEntry { id: string; to: string; label: ReactNode; sub?: string; plainLabel: string; updated_at: string }

/** A sidebar history (quizzes, guides): grouped by date like the chats, with a hover menu that deletes an item after a confirmation. */
export function HistoryList({
  items, error, retry, emptyText, confirmTitle, confirmText, onDelete, isActive, heading,
}: {
  items: HistoryEntry[] | null; error: string | null; retry: () => void; emptyText: string; confirmTitle: string; confirmText: (e: HistoryEntry) => string;
  onDelete: (e: HistoryEntry) => Promise<void>; isActive?: (e: HistoryEntry) => boolean; heading?: string;
}) {
  const [deleting, setDeleting] = useState<HistoryEntry | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function confirm() {
    if (!deleting) return;
    setBusy(true); setErr(null);
    try { await onDelete(deleting); setDeleting(null); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }

  const groups = items ? groupByDate(items, (i) => i.updated_at) : [];
  return (
    <div className="px-3 pb-3">
      {heading && <h2 className="px-2 pb-1 pt-1 font-serif text-[13px] font-normal italic text-side-faint">{heading}</h2>}
      {items === null && !error ? (
        <div className="space-y-3 px-2 pt-2" aria-label="Loading history">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-4 !bg-side-hover" />)}</div>
      ) : error && items === null ? (
        <div className="px-2 pt-2 text-[13px] text-side-muted"><p>{error}</p><button onClick={retry} className="mt-1 underline underline-offset-2 hover:text-side-ink">Try again</button></div>
      ) : groups.length === 0 ? (
        <p className="px-2 pt-2 text-[13px] text-side-muted">{emptyText}</p>
      ) : (
        groups.map((g) => (
          <section key={g.label} className="mt-3 first:mt-1">
            <h3 className="px-2 pb-1 font-serif text-[13px] font-normal italic text-side-faint">{g.label}</h3>
            <ul>
              {g.items.map((e) => {
                const current = isActive?.(e) ?? false;
                return (
                  <li key={e.id} className="group relative">
                    <NavLink to={e.to} className={cn("block rounded-md py-1.5 pl-2 pr-8 text-[14px] leading-snug transition-colors duration-150 hover:bg-side-hover", current ? "font-semibold text-side-ink" : "text-[#E9E1D4]")}>
                      <span className="block truncate" title={e.plainLabel}>{e.label}</span>
                      {e.sub && <span className="block truncate text-[12px] font-normal text-side-muted">{e.sub}</span>}
                    </NavLink>
                    <Menu>
                      <MenuTrigger aria-label={`Options for ${e.plainLabel}`}
                        className="absolute right-1 top-2 rounded-md p-1 text-side-muted opacity-0 transition-opacity hover:text-side-ink focus-visible:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100 max-lg:opacity-100">
                        <MoreHorizontal size={16} strokeWidth={1.5} />
                      </MenuTrigger>
                      <MenuContent align="end">
                        <MenuItem onSelect={() => { setErr(null); setDeleting(e); }}><Trash2 size={14} strokeWidth={1.5} /> Delete</MenuItem>
                      </MenuContent>
                    </Menu>
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}
      <Dialog open={Boolean(deleting)} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent title={confirmTitle} description={deleting ? confirmText(deleting) : undefined}>
          {err && <p role="alert" className="mb-2 text-[13px] text-accent">{err}</p>}
          <div className="flex justify-end gap-2">
            <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button onClick={() => void confirm()} disabled={busy}>Delete</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
