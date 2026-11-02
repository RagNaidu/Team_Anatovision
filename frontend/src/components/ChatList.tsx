import { useState } from "react";
import { NavLink, useNavigate, useParams } from "react-router-dom";
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { useData } from "@/state/data";
import { errorMessage } from "@/lib/api";
import { groupChats, cn } from "@/lib/utils";
import type { ChatSummary } from "@/lib/types";
import { Skeleton } from "@/components/ui/misc";
import { Menu, MenuContent, MenuItem, MenuTrigger } from "@/components/ui/dropdown";
import { Dialog, DialogClose, DialogContent } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

export function ChatList() {
  const { chats, chatsLoading, chatsError, refreshChats, renameChat, removeChat } = useData();
  const { chatId } = useParams();
  const navigate = useNavigate();
  const [renaming, setRenaming] = useState<ChatSummary | null>(null);
  const [deleting, setDeleting] = useState<ChatSummary | null>(null);
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const groups = groupChats(chats);

  async function doRename() {
    if (!renaming) return;
    setBusy(true); setErr(null);
    try { await renameChat(renaming.id, title.trim()); setRenaming(null); } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }
  async function doDelete() {
    if (!deleting) return;
    setBusy(true); setErr(null);
    try {
      await removeChat(deleting.id);
      if (deleting.id === chatId) navigate("/ask");
      setDeleting(null);
    } catch (e) { setErr(errorMessage(e)); } finally { setBusy(false); }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <nav aria-label="Chat history" className="scroll-side min-h-0 flex-1 overflow-y-auto px-3 pb-3">
        {chatsLoading && chats.length === 0 ? (
          <div className="space-y-3 px-2 pt-3" aria-label="Loading chats">
            <Skeleton className="h-3 w-16 !bg-side-hover" />
            {[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-4 !bg-side-hover" />)}
          </div>
        ) : chatsError ? (
          <div className="px-2 pt-3 text-[13px] text-side-muted">
            <p>{chatsError}</p>
            <button onClick={() => void refreshChats()} className="mt-1 underline underline-offset-2 hover:text-side-ink">Try again</button>
          </div>
        ) : groups.length === 0 ? (
          <p className="px-2 pt-3 text-[13px] text-side-muted">No chats yet. Your questions will be listed here.</p>
        ) : (
          groups.map((g) => (
            <section key={g.label} className="mt-4 first:mt-2">
              <h2 className="px-2 pb-1 font-serif text-[13px] font-normal italic text-side-faint">{g.label}</h2>
              <ul>
                {g.chats.map((c) => {
                  const current = c.id === chatId;
                  return (
                    <li key={c.id} className="group relative">
                      <NavLink to={`/ask/${c.id}`}
                        className={cn("flex items-center gap-2 rounded-md py-1.5 pr-8 text-[14px] leading-snug transition-colors duration-150 hover:bg-side-hover", current ? "pl-2 font-semibold text-side-ink" : "pl-5 text-[#E9E1D4]")}>
                        {current && <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-side-logo" aria-hidden />}
                        <span className="truncate" title={c.title}>{c.title}</span>
                        {current && <span className="sr-only">(current chat)</span>}
                      </NavLink>
                      <Menu>
                        <MenuTrigger aria-label={`Options for ${c.title}`}
                          className="absolute right-1 top-1/2 -translate-y-1/2 rounded-md p-1 text-side-muted opacity-0 transition-opacity hover:text-side-ink focus-visible:opacity-100 group-hover:opacity-100 data-[state=open]:opacity-100 max-lg:opacity-100">
                          <MoreHorizontal size={16} strokeWidth={1.5} />
                        </MenuTrigger>
                        <MenuContent align="end">
                          <MenuItem onSelect={() => { setTitle(c.title); setErr(null); setRenaming(c); }}><Pencil size={14} strokeWidth={1.5} /> Rename</MenuItem>
                          <MenuItem onSelect={() => { setErr(null); setDeleting(c); }}><Trash2 size={14} strokeWidth={1.5} /> Delete</MenuItem>
                        </MenuContent>
                      </Menu>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))
        )}
      </nav>
      <p className="px-5 pb-2 text-[12px] text-side-faint">Chats are kept for 90 days</p>

      <Dialog open={Boolean(renaming)} onOpenChange={(o) => !o && setRenaming(null)}>
        <DialogContent title="Rename chat">
          <form onSubmit={(e) => { e.preventDefault(); void doRename(); }}>
            <label htmlFor="rename-chat" className="sr-only">Chat name</label>
            <input id="rename-chat" autoFocus value={title} onChange={(e) => setTitle(e.target.value)} maxLength={80}
              className="h-10 w-full rounded-md border border-line-strong bg-bone px-3 text-[15px]" />
            {err && <p role="alert" className="mt-2 text-[13px] text-accent">{err}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
              <Button type="submit" disabled={busy || !title.trim()}>Save</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
      <Dialog open={Boolean(deleting)} onOpenChange={(o) => !o && setDeleting(null)}>
        <DialogContent title="Delete this chat?" description={deleting ? `“${deleting.title}” will be removed. This can't be undone.` : undefined}>
          {err && <p role="alert" className="mb-2 text-[13px] text-accent">{err}</p>}
          <div className="flex justify-end gap-2">
            <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button onClick={() => void doDelete()} disabled={busy}>Delete</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
