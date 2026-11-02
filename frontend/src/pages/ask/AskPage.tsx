import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowDown } from "lucide-react";
import { api, errorMessage } from "@/lib/api";
import type { AnswerLength, Message } from "@/lib/types";
import { useData } from "@/state/data";
import { useAuth } from "@/state/auth";
import { bodyTypeString, store, type BodyType, shortLecture } from "@/lib/utils";
import { useStickToBottom } from "@/hooks/useStickToBottom";
import { useAskProgress, type StageView } from "@/hooks/useAskProgress";
import { ProgressRow } from "@/components/ProgressRow";
import { Skeleton, Notice } from "@/components/ui/misc";
import { Button } from "@/components/ui/button";
import { Composer, type ComposerHandle } from "./Composer";
import { AssistantMessage, UserMessage } from "./MessageItem";
import { SourcePanelHost } from "./SourcePanel";

/** The message column: a fixed 56 px (40 + the 16 px padding) from the sidebar on desktop (centred on tablet and phone), never wider than 700 px; header, messages and composer share it. */
const COLUMN = "w-full max-w-[700px] mx-auto lg:mx-0 lg:ml-10";

const EXAMPLES = [
  "What are the boundaries and contents of the femoral triangle?",
  "apex",
  "How do I expose the femoral triangle?",
  "What is the nerve supply of the hypothenar muscles?",
];

type Item =
  | { type: "msg"; msg: Message; fresh?: boolean; stages?: StageView[]; local?: boolean }
  | { type: "pending"; id: string; requestId: string }
  | { type: "failed"; id: string; question: string; error: string };

function newRequestId(): string {
  try { return crypto.randomUUID(); } catch { return `r${Date.now()}${Math.random().toString(36).slice(2, 8)}`; }
}

function Pending({ requestId, onStages }: { requestId: string; onStages: (id: string, s: StageView[]) => void }) {
  const { available, stages } = useAskProgress(requestId, true);
  useEffect(() => { onStages(requestId, stages); }, [stages, requestId, onStages]);
  return <ProgressRow phase="waiting" stages={available ? stages : undefined} />;
}

export default function AskPage() {
  const { chatId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const { user, preview } = useAuth();
  const { scope, chats, refreshChats } = useData();

  const [items, setItems] = useState<Item[]>([]);
  const [title, setTitle] = useState("New chat");
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [length, setLength] = useState<AnswerLength>(() => store.get<AnswerLength>("av_length", "brief"));
  const [selected, setSelected] = useState<string[]>([]);
  const [body, setBody] = useState<BodyType | null>(() => store.get<BodyType | null>("av_body", null));
  const [panel, setPanel] = useState<{ messageId: string; n: number } | null>(null);
  const composer = useRef<ComposerHandle>(null);
  const justCreated = useRef<string | null>(null);
  const stagesRef = useRef(new Map<string, StageView[]>());
  const pendingCount = items.filter((i) => i.type === "pending").length;
  const busy = pendingCount > 0;
  const { scrollRef, contentRef, atBottom, toBottom } = useStickToBottom();

  const onStages = useCallback((id: string, s: StageView[]) => { stagesRef.current.set(id, s); }, []);
  useEffect(() => { store.set("av_length", length); }, [length]);
  useEffect(() => { store.set("av_body", body); }, [body]);

  // Load a chat when the URL names one; reset when it does not ("New chat").
  useEffect(() => {
    setPanel(null);
    if (!chatId) { setItems([]); setTitle("New chat"); setLoadError(null); setLoading(false); setSelected([]); composer.current?.focus(); return; }
    if (justCreated.current === chatId) { justCreated.current = null; return; }
    let live = true;
    setLoading(true); setLoadError(null); setItems([]);
    api.getChat(chatId)
      .then((c) => {
        if (!live) return;
        setTitle(c.title);
        setItems(c.messages.map((m) => ({ type: "msg", msg: m })));
        setLoading(false);
        requestAnimationFrame(() => toBottom(false));
      })
      .catch((e) => { if (live) { setLoadError(errorMessage(e)); setLoading(false); } });
    return () => { live = false; };
  }, [chatId, location.state, toBottom]);

  // Title follows the sidebar (rename) and the first question.
  useEffect(() => { const c = chats.find((x) => x.id === chatId); if (c) setTitle(c.title); }, [chats, chatId]);

  const send = useCallback(async (question: string, opts?: { length?: AnswerLength; retryOf?: string }) => {
    let id = chatId;
    const requestId = newRequestId();
    const asked = new Date().toISOString();
    try {
      if (!id) {
        // the header shows the question as the title until the backend's own title arrives with the chat list
        setTitle(question.length > 48 ? question.slice(0, 48).replace(/\s+\S*$/, "") + "…" : question);
        const c = await api.createChat();
        id = c.id;
        justCreated.current = id;
        navigate(`/ask/${id}`, { replace: true });
      }
    } catch (e) {
      setItems((is) => [...is, { type: "failed", id: requestId, question, error: errorMessage(e) }]);
      return;
    }
    const chat = id;
    if (!opts?.retryOf) {
      const u: Message = { id: `local-${requestId}`, role: "user", created_at: asked, kind: "answer", markdown: question, sources: [], footer: null, timing_ms: 0 };
      setItems((is) => [...is, { type: "msg", msg: u, local: true }, { type: "pending", id: requestId, requestId }]);
    } else {
      setItems((is) => [...is.filter((i) => !(i.type === "failed" && i.id === opts.retryOf)), { type: "pending", id: requestId, requestId }]);
    }
    requestAnimationFrame(() => toBottom(true));
    try {
      const a = await api.ask({
        chat_id: chat, question, length: opts?.length ?? length,
        ...(selected.length ? { lecture_ids: selected } : {}),
        ...(body ? { body_type: bodyTypeString(body) } : {}),
      }, requestId);
      const seen = stagesRef.current.get(requestId) ?? [];
      const known = seen.reduce((t, s) => t + (s.seconds ?? 0), 0);
      const stages = seen.map((s, i): StageView => ({ ...s, state: "done", seconds: s.seconds ?? (i === seen.length - 1 ? Math.max(0, Math.round((a.timing_ms / 1000 - known) * 10) / 10) : null) }));
      stagesRef.current.delete(requestId);
      setItems((is) => is.map((i) => (i.type === "pending" && i.id === requestId ? { type: "msg", msg: a, fresh: true, stages } : i)));
      void refreshChats();
    } catch (e) {
      stagesRef.current.delete(requestId);
      setItems((is) => is.map((i) => (i.type === "pending" && i.id === requestId ? { type: "failed", id: requestId, question, error: errorMessage(e) } : i)));
    }
  }, [chatId, navigate, length, selected, body, toBottom, refreshChats]);

  const panelMsg = useMemo(() => {
    if (!panel) return null;
    for (const i of items) if (i.type === "msg" && i.msg.id === panel.messageId) return i.msg;
    return null;
  }, [panel, items]);

  const openSource = useCallback((messageId: string, n: number) => setPanel({ messageId, n }), []);
  const lastQuestionBefore = (idx: number) => {
    for (let k = idx - 1; k >= 0; k--) { const it = items[k]; if (it.type === "msg" && it.msg.role === "user") return it.msg.markdown; }
    return null;
  };

  const scopeLabel = selected.length === 0 ? null : selected.length === 1 ? shortLecture(scope?.lectures.find((l) => l.id === selected[0])?.title ?? "1 lecture") : `${selected.length} lectures`;
  const empty = !loading && !loadError && items.length === 0;

  return (
    <div className="flex h-full min-h-0">
      <section className="flex min-w-0 flex-1 flex-col" aria-label="Chat">
        <header className="shrink-0">
          <div className={`flex h-14 items-center justify-between gap-4 px-4 ${COLUMN}`}>
            <h1 className="truncate font-serif text-[20px] font-semibold text-ink">{title}</h1>
            {scopeLabel && <span className="serif-label shrink-0">{scopeLabel}</span>}
          </div>
        </header>

        <div ref={scrollRef} className="scroll-quiet relative min-h-0 flex-1 overflow-y-auto" data-testid="chat-scroll">
          <div ref={contentRef} className={`px-4 pb-6 pt-2 ${COLUMN}`}>
            {loading ? (
              <div className="space-y-4 pt-6" aria-label="Loading chat">
                <Skeleton className="ml-auto h-10 w-2/5 !rounded-2xl" />
                <Skeleton className="h-4" /><Skeleton className="h-4 w-11/12" /><Skeleton className="h-4 w-4/5" /><Skeleton className="h-4 w-2/3" />
              </div>
            ) : loadError ? (
              <Notice tone="error" className="mt-8" action={<Link to="/ask" className="shrink-0 text-accent underline underline-offset-2">New chat</Link>}>{loadError}</Notice>
            ) : empty ? (
              <div className="pt-[10vh]">
                <h2 className="font-serif text-[30px] font-semibold leading-tight text-ink max-sm:text-[26px]">What would you like to know?</h2>
                <p className="serif-label mt-1">{preview ? "Previewing: nothing you ask is saved." : `Hello, ${user?.name.split(" ")[0] ?? "there"}. Ask about a structure, region or dissection step.`}</p>
                <ul className="mt-8 divide-y divide-line border-y border-line">
                  {EXAMPLES.map((q) => (
                    <li key={q}>
                      <button type="button" onClick={() => void send(q)} disabled={busy}
                        className="w-full px-1 py-3 text-left text-[15px] text-body-2 transition-colors duration-150 hover:bg-surface-2 hover:text-ink disabled:opacity-50">{q}</button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="space-y-6 pt-4">
                <AnimatePresence initial={false}>
                  {items.map((it, idx) => {
                    if (it.type === "msg") {
                      return it.msg.role === "user" ? (
                        <UserMessage key={it.msg.id} message={it.msg} animate={Boolean(it.local)} />
                      ) : (
                        <AssistantMessage key={it.msg.id} message={it.msg} fresh={it.fresh} stages={it.stages} animate={Boolean(it.fresh)}
                          activeN={panel?.messageId === it.msg.id ? panel.n : null} onOpenSource={openSource}
                          onRetry={it.msg.kind === "error" ? () => { const q = lastQuestionBefore(idx); if (q) void send(q, { retryOf: it.msg.id }); } : undefined} />
                      );
                    }
                    if (it.type === "pending") {
                      return <motion.div key={it.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, height: 0 }} transition={{ duration: 0.2 }}><Pending requestId={it.requestId} onStages={onStages} /></motion.div>;
                    }
                    return (
                      <motion.div key={it.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
                        <Notice tone="error" action={<Button size="sm" variant="outline" onClick={() => void send(it.question, { retryOf: it.id })}>Try again</Button>}>{it.error}</Notice>
                      </motion.div>
                    );
                  })}
                </AnimatePresence>
              </div>
            )}
          </div>
        </div>

        <div className="relative shrink-0 pb-4 pt-1">
          <AnimatePresence>
            {!atBottom && items.length > 0 && (
              <motion.button key="latest" type="button" onClick={() => toBottom(true)} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: 6 }}
                className="absolute -top-9 left-1/2 z-10 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-line-strong bg-surface px-3 py-1 text-[13px] text-body-2 shadow-float hover:bg-surface-2">
                <ArrowDown size={14} strokeWidth={1.75} aria-hidden /> Latest
              </motion.button>
            )}
          </AnimatePresence>
          <div className={`px-4 ${COLUMN}`}>
            <Composer ref={composer} disabled={busy || loading} length={length} onLength={setLength} lectures={scope?.lectures ?? null}
              selected={selected} onSelected={setSelected} body={body} onBody={setBody} onSend={(q) => void send(q)} />
          </div>
        </div>
      </section>

      <SourcePanelHost open={Boolean(panel && panelMsg)} sources={panelMsg?.sources ?? []} activeN={panel?.n ?? 0}
        onSelect={(n) => panel && setPanel({ messageId: panel.messageId, n })} onClose={() => setPanel(null)}
        onExplain={(snippet) => {
          const cut = snippet.length > 540 ? snippet.slice(0, 540).replace(/\s+\S*$/, "") + "…" : snippet;
          void send(`Explain this more simply: ${cut}`, { length: "brief" });
        }}
        quiz />
    </div>
  );
}
