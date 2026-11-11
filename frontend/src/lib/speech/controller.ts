/**
 * Voice dictation, without React: a thin state machine around the browser's SpeechRecognition.
 * Nothing here stores or logs audio or text; the text only goes to the callbacks you pass in.
 * Self-contained on purpose (no project imports), so it can be unit-tested with plain `node --test`.
 */

// ---- the small part of the Web Speech API that we use (the DOM lib does not ship these types) ----
export interface SpeechAlternativeLike { transcript: string }
export interface SpeechResultLike { isFinal: boolean; length: number; [i: number]: SpeechAlternativeLike }
export interface SpeechEventLike { resultIndex: number; results: { length: number; [i: number]: SpeechResultLike } }
export interface RecognitionLike {
  lang: string; continuous: boolean; interimResults: boolean; maxAlternatives?: number;
  onresult: ((e: SpeechEventLike) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  onstart?: (() => void) | null;
  start(): void; stop(): void; abort(): void;
}
export type RecognitionCtor = new () => RecognitionLike;

export type VoiceState = "idle" | "listening" | "error";
export type VoiceErrorKind = "denied" | "insecure" | "unsupported" | "no-speech" | "no-mic" | "network" | "other";

export const VOICE_MESSAGES: Record<VoiceErrorKind, string> = {
  denied: "The microphone is blocked. Allow it in your browser's site settings, then tap the mic again.",
  insecure: "Voice input needs a secure page (https or localhost). It is not available on this address.",
  unsupported: "Voice input works in Chrome, Edge and Safari",
  "no-speech": "I didn't hear anything. Tap the mic and try again.",
  "no-mic": "No microphone was found. Check that one is connected, then try again.",
  network: "The browser's speech service could not be reached. Check your connection and try again.",
  other: "Voice input stopped unexpectedly. Tap the mic to try again.",
};

/** What an interpreter makes of one finished phrase: the words to keep in the text box, and an optional action to run afterwards. */
export interface Interpreted { keep: string; action?: () => void }
export type Interpret = (phrase: string) => Interpreted | null;

export interface ControllerOptions {
  ctor: RecognitionCtor | null;
  /** The text already in the box when listening starts: dictation is appended to it. */
  getText: () => string;
  /** Called whenever the full text changes (existing text + final phrases + the interim phrase still being spoken). */
  onText: (text: string) => void;
  onState?: (state: VoiceState, error: VoiceErrorKind | null) => void;
  /** Optional spoken commands (the quiz): each finished phrase is run through it. Without it the words are just text. */
  interpret?: Interpret | null;
  lang?: string;
  silenceMs?: number | (() => number);
  /** Time allowed at the start before anything was said (longer than the silence time, so there is room to begin). */
  graceMs?: number;
  maxLength?: number;
  secure?: () => boolean;
  timers?: { set: (fn: () => void, ms: number) => unknown; clear: (t: unknown) => void };
}

export function recognitionCtor(w: { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor } | undefined | null): RecognitionCtor | null {
  return (w && (w.SpeechRecognition || w.webkitSpeechRecognition)) || null;
}

/** Join pieces with single spaces: dictation never glues words together or doubles the gap. */
export function joinText(...parts: string[]): string {
  return parts.map((p) => p.trim()).filter(Boolean).join(" ");
}

export class SpeechController {
  state: VoiceState = "idle";
  error: VoiceErrorKind | null = null;
  private rec: RecognitionLike | null = null;
  private base = "";
  private timer: unknown = null;
  private heardAny = false;
  private muted = false;
  /** per result index: the text of a final phrase after the interpreter has seen it (so a phrase is never interpreted twice) */
  private done = new Map<number, string>();
  private pending: Array<() => void> = [];
  private last = "";

  private o: ControllerOptions;
  constructor(o: ControllerOptions) { this.o = o; }

  get supported() { return this.o.ctor !== null; }
  get listening() { return this.state === "listening"; }

  private set(state: VoiceState, error: VoiceErrorKind | null = null) {
    this.state = state; this.error = error;
    this.o.onState?.(state, error);
  }
  private t = {
    set: (fn: () => void, ms: number) => (this.o.timers ? this.o.timers.set(fn, ms) : setTimeout(fn, ms)),
    clear: (h: unknown) => (this.o.timers ? this.o.timers.clear(h) : clearTimeout(h as ReturnType<typeof setTimeout>)),
  };
  private silence() { const v = this.o.silenceMs; return (typeof v === "function" ? v() : v) ?? 3000; }
  private arm(ms: number) {
    if (this.timer !== null) this.t.clear(this.timer);
    this.timer = this.t.set(() => this.stop(), ms);
  }
  private disarm() { if (this.timer !== null) { this.t.clear(this.timer); this.timer = null; } }

  start(): boolean {
    if (this.state === "listening") return true;
    if (!this.o.ctor) { this.set("error", "unsupported"); return false; }
    const secure = this.o.secure ? this.o.secure() : (typeof window === "undefined" ? true : window.isSecureContext !== false);
    if (!secure) { this.set("error", "insecure"); return false; }
    let rec: RecognitionLike;
    try { rec = new this.o.ctor(); } catch { this.set("error", "other"); return false; }
    rec.lang = this.o.lang ?? "en-US";
    rec.continuous = true;
    rec.interimResults = true;
    rec.maxAlternatives = 1;
    this.base = this.o.getText();
    this.last = this.base;
    this.done.clear(); this.pending = []; this.heardAny = false; this.muted = false;
    rec.onresult = (e) => this.onResult(e);
    rec.onerror = (e) => this.onError(e.error);
    rec.onend = () => this.onEnd();
    this.rec = rec;
    try { rec.start(); } catch { this.rec = null; this.set("error", "other"); return false; }
    this.set("listening");
    this.arm(this.o.graceMs ?? Math.max(this.silence(), 6000));
    return true;
  }

  stop() {
    if (this.state !== "listening" || !this.rec) return;
    this.disarm();
    try { this.rec.stop(); } catch { /* already stopped */ }
  }

  /** Stop AND ignore anything the engine still delivers: the text box is now the person's (they sent it or typed into it). */
  finish() { this.muted = true; this.stop(); }

  /** Close without waiting (leaving the page). */
  abort() {
    this.disarm();
    const r = this.rec; this.rec = null;
    if (r) { r.onresult = r.onerror = r.onend = null; try { r.abort(); } catch { /* ignore */ } }
    if (this.state === "listening") this.set("idle");
  }

  toggle() { if (this.state === "listening") this.stop(); else this.start(); }

  clearError() { if (this.state === "error") this.set("idle"); }

  /** The text as it stands now (what a command such as "send" acts on). */
  get text() { return this.last; }

  private onResult(e: SpeechEventLike) {
    if (this.muted) return;
    this.heardAny = true;
    this.arm(this.silence());
    let spoken = "";
    for (let i = 0; i < e.results.length; i++) {
      const r = e.results[i];
      const raw = (r[0]?.transcript ?? "").trim();
      if (!r.isFinal) { spoken = joinText(spoken, raw); continue; }
      let text = this.done.get(i);
      if (text === undefined) {
        text = raw;
        const it = this.o.interpret ? this.o.interpret(raw) : null;
        if (it) { text = it.keep; if (it.action) this.pending.push(it.action); }
        this.done.set(i, text);
      }
      spoken = joinText(spoken, text);
    }
    this.push(joinText(this.base, spoken));
    const run = this.pending; this.pending = [];
    for (const a of run) a();
  }

  private push(text: string) {
    const t = this.o.maxLength ? text.slice(0, this.o.maxLength) : text;
    if (t !== this.last) { this.last = t; this.o.onText(t); }
  }

  private onError(code: string) {
    // "aborted" is what stop()/abort() cause; "no-speech" with nothing said is a quiet end, not a fault
    if (code === "aborted") return;
    this.disarm();
    const kind: VoiceErrorKind =
      code === "not-allowed" || code === "service-not-allowed" ? "denied"
      : code === "no-speech" ? "no-speech"
      : code === "audio-capture" ? "no-mic"
      : code === "network" ? "network" : "other";
    this.rec = null;
    this.set("error", kind);
  }

  private onEnd() {
    this.disarm();
    this.rec = null;
    if (this.state === "listening") this.set("idle");
  }

  get wasHeard() { return this.heardAny; }
}
