import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from "react";
import { ArrowUp, ChevronDown, Lock } from "lucide-react";
import { cn, BODY_LEVELS, type BodyType } from "@/lib/utils";
import { Popover, PopoverContent, PopoverTrigger, PopoverClose } from "@/components/ui/popover";
import { Checkbox } from "@/components/ui/checkbox";
import { Select } from "@/components/ui/misc";
import type { AnswerLength, ScopeLecture } from "@/lib/types";

export const MAX_Q = 600;
export interface ComposerHandle { focus: () => void }

interface Props {
  disabled?: boolean;
  length: AnswerLength;
  onLength: (l: AnswerLength) => void;
  lectures: ScopeLecture[] | null;
  selected: string[];
  onSelected: (ids: string[]) => void;
  body: BodyType | null;
  onBody: (b: BodyType | null) => void;
  onSend: (q: string) => void;
}

export const Composer = forwardRef<ComposerHandle, Props>(function Composer({ disabled, length, onLength, lectures, selected, onSelected, body, onBody, onSend }, ref) {
  const [text, setText] = useState("");
  const ta = useRef<HTMLTextAreaElement>(null);
  useImperativeHandle(ref, () => ({ focus: () => ta.current?.focus() }));
  useLayoutEffect(() => {
    const el = ta.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);
  useEffect(() => { ta.current?.focus(); }, []);

  const trimmed = text.trim();
  const can = trimmed.length > 0 && !disabled && text.length <= MAX_Q;
  function send() {
    if (!can) return;
    onSend(trimmed);
    setText("");
  }
  const granted = lectures?.filter((l) => l.granted) ?? [];
  const scopeLabel = selected.length === 0 ? "All lectures" : selected.length === 1 ? (lectures?.find((l) => l.id === selected[0])?.title.match(/^Lecture\s+\d+\w*/)?.[0] ?? "1 lecture") : `${selected.length} lectures`;
  const bodyLabel = body ? `${body.fat} fat · ${body.muscle} muscle · ${body.build}` : "Body type";

  return (
    <div className="rounded-[18px] border border-line-strong bg-surface p-3 shadow-float">
      <label htmlFor="composer" className="sr-only">Ask about a structure, region or dissection step</label>
      <textarea
        id="composer" ref={ta} rows={1} value={text} maxLength={MAX_Q + 40}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); }
        }}
        placeholder="Ask about a structure, region or dissection step"
        className="block max-h-[200px] w-full resize-none bg-transparent px-1.5 py-1 text-[15px] leading-relaxed text-ink outline-none placeholder:text-muted focus-visible:outline-none"
      />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <div role="radiogroup" aria-label="Answer length" className="inline-flex rounded-full border border-line-strong bg-bone p-0.5">
          {(["brief", "detailed"] as const).map((l) => (
            <button key={l} type="button" role="radio" aria-checked={length === l} onClick={() => onLength(l)}
              className={cn("h-7 rounded-full px-3 text-[13px] capitalize transition-colors duration-150", length === l ? "bg-user-bubble text-user-bubble-ink" : "text-body-2 hover:bg-surface-2")}>
              {l === "brief" ? "Brief" : "Detailed"}
            </button>
          ))}
        </div>

        <Popover>
          <PopoverTrigger className={cn("inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] hover:bg-surface-2", selected.length ? "border-accent text-accent" : "border-line-strong text-body-2")}>
            {scopeLabel} <ChevronDown size={14} strokeWidth={1.5} aria-hidden />
          </PopoverTrigger>
          <PopoverContent align="start" className="w-80">
            <p className="serif-label mb-2">Limit this question to</p>
            {!lectures ? <p className="text-[13px] text-muted">Loading lectures…</p> : (
              <ul className="max-h-64 space-y-0.5 overflow-y-auto scroll-quiet">
                <li>
                  <label className="flex cursor-pointer items-center gap-2.5 rounded-md px-1.5 py-1.5 text-[14px] hover:bg-surface-2">
                    <Checkbox checked={selected.length === 0} onCheckedChange={() => onSelected([])} aria-label="All lectures" /> All lectures I can open
                  </label>
                </li>
                {lectures.map((l) => (
                  <li key={l.id}>
                    <label className={cn("flex items-center gap-2.5 rounded-md px-1.5 py-1.5 text-[14px]", l.granted ? "cursor-pointer hover:bg-surface-2" : "cursor-not-allowed text-muted")}>
                      <Checkbox disabled={!l.granted} checked={selected.includes(l.id)}
                        onCheckedChange={(c) => onSelected(c ? [...selected, l.id] : selected.filter((x) => x !== l.id))} aria-label={l.title} />
                      <span className="min-w-0 flex-1 truncate">{l.title}</span>
                      {!l.granted && <span className="flex shrink-0 items-center gap-1 text-[12px]"><Lock size={12} strokeWidth={1.5} aria-hidden />Ask your instructor</span>}
                    </label>
                  </li>
                ))}
                {granted.length === 0 && <li className="px-1.5 py-1 text-[13px] text-muted">No lectures are open to you yet.</li>}
              </ul>
            )}
          </PopoverContent>
        </Popover>

        <Popover>
          <PopoverTrigger className={cn("inline-flex h-8 items-center gap-1.5 rounded-full px-3 text-[13px] hover:bg-surface-2", body ? "border border-line-strong text-body-2" : "text-muted")}>
            {bodyLabel} <ChevronDown size={14} strokeWidth={1.5} aria-hidden />
          </PopoverTrigger>
          <PopoverContent align="start" className="w-72">
            <p className="serif-label mb-1">Cadaver body type</p>
            <p className="mb-3 text-[13px] text-muted">Sent with each question. Choose it once at the start of your lab session.</p>
            <div className="space-y-2.5">
              {([["fat", "Fat", "fat"], ["muscle", "Muscle", "muscle"], ["build", "Build", "build"]] as const).map(([k, label]) => (
                <div key={k} className="flex items-center justify-between gap-3">
                  <label htmlFor={`bt-${k}`} className="text-[14px] text-body-2">{label}</label>
                  <Select id={`bt-${k}`} value={body?.[k] ?? ""} className="w-36"
                    onChange={(e) => onBody({ fat: body?.fat ?? "average", muscle: body?.muscle ?? "average", build: body?.build ?? "average", [k]: e.target.value })}>
                    <option value="" disabled>Choose</option>
                    {BODY_LEVELS[k].map((v) => <option key={v} value={v}>{v}</option>)}
                  </Select>
                </div>
              ))}
            </div>
            <div className="mt-3 flex justify-end">
              <PopoverClose asChild><button type="button" onClick={() => onBody(null)} className="text-[13px] text-muted underline underline-offset-2 hover:text-ink">Clear</button></PopoverClose>
            </div>
          </PopoverContent>
        </Popover>

        <div className="flex-1" />
        <span className={cn("text-[12px] tabular-nums", text.length >= MAX_Q ? "font-medium text-accent" : text.length >= 550 ? "text-warn" : "text-muted")} aria-live="off">
          {text.length} / {MAX_Q}
        </span>
        <button type="button" onClick={send} disabled={!can} aria-label="Send question"
          className="flex h-9 w-9 items-center justify-center rounded-full bg-accent text-accent-fg transition-colors duration-150 hover:bg-accent-hover disabled:opacity-40">
          <ArrowUp size={18} strokeWidth={2} />
        </button>
      </div>
    </div>
  );
});
