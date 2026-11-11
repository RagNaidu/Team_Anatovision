import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  SpeechController, recognitionCtor, VOICE_MESSAGES,
  type Interpret, type RecognitionCtor, type VoiceErrorKind, type VoiceState,
} from "@/lib/speech/controller";

const USED_KEY = "av_voice_used";
const seen = () => { try { return localStorage.getItem(USED_KEY) === "1"; } catch { return false; } };
const markSeen = () => { try { localStorage.setItem(USED_KEY, "1"); } catch { /* private window: the note simply shows again */ } };

export interface SpeechInputOptions {
  /** The text already in the box when listening starts. Dictation is appended to it. */
  getText: () => string;
  /** Live text: existing text + final phrases + the interim phrase. */
  onText: (text: string) => void;
  /** Spoken commands (the quiz only). Without it the words are just text, and nothing is ever sent by voice. */
  interpret?: Interpret;
  maxLength?: number;
  silenceMs?: number;
}

export interface SpeechInput {
  supported: boolean;
  state: VoiceState;
  listening: boolean;
  error: VoiceErrorKind | null;
  message: string | null;
  /** The privacy line shows until the person has used voice once in this browser. */
  firstUse: boolean;
  toggle: () => void;
  stop: () => void;
  /** Stop and ignore late words: call when the text is sent. */
  finish: () => void;
  /** Call from the box's own onChange: typing while listening ends listening, so the person's edit is never overwritten. */
  userEdited: () => void;
  dismissError: () => void;
}

/** Browser dictation (Web Speech API). No backend, no audio or text is kept: the text only goes to onText. */
export function useSpeechInput(opts: SpeechInputOptions): SpeechInput {
  const ref = useRef(opts); ref.current = opts;
  const [state, setState] = useState<VoiceState>("idle");
  const [error, setError] = useState<VoiceErrorKind | null>(null);
  const [firstUse, setFirstUse] = useState(() => !seen());
  const ctor = useMemo<RecognitionCtor | null>(() => (typeof window === "undefined" ? null : recognitionCtor(window as never)), []);

  const ctl = useRef<SpeechController | null>(null);
  if (!ctl.current) {
    const c = new SpeechController({
      ctor,
      getText: () => ref.current.getText(),
      onText: (t) => ref.current.onText(t),
      onState: (s, e) => { setState(s); setError(e); },
      interpret: (phrase) => ref.current.interpret?.(phrase) ?? null,
      silenceMs: () => ref.current.silenceMs ?? 3000,
      maxLength: opts.maxLength,
    });
    ctl.current = c;
  }
  useEffect(() => () => ctl.current?.abort(), []);

  const toggle = useCallback(() => {
    const c = ctl.current!;
    if (c.listening) { c.stop(); return; }
    if (c.start()) { markSeen(); setFirstUse(false); }
  }, []);
  const stop = useCallback(() => ctl.current?.stop(), []);
  const finish = useCallback(() => { if (ctl.current?.listening) ctl.current.finish(); }, []);
  const userEdited = finish;
  const dismissError = useCallback(() => ctl.current?.clearError(), []);

  return { supported: ctor !== null, state, listening: state === "listening", error, message: error ? VOICE_MESSAGES[error] : null, firstUse, toggle, stop, finish, userEdited, dismissError };
}
