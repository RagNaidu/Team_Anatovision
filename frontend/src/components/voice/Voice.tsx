import { Info, Mic, MicOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { VOICE_MESSAGES } from "@/lib/speech/controller";
import type { SpeechInput } from "@/hooks/useSpeechInput";

export const PRIVACY_NOTE = "Voice is processed by your browser's speech service.";

/**
 * The microphone button: a small plain icon. Tap to start, tap to stop.
 * idle = grey mic, listening = red mic + pulsing dot + "Listening…", error = crossed red mic.
 * Without browser support the button is not drawn; a small info mark carries the one-line reason.
 */
export function MicButton({ voice, label = "voice input", className }: { voice: SpeechInput; label?: string; className?: string }) {
  if (!voice.supported) {
    return (
      <span className={cn("group relative inline-flex", className)}>
        <button type="button" aria-label={VOICE_MESSAGES.unsupported} data-testid="voice-unsupported"
          className="flex h-8 w-8 items-center justify-center rounded-full text-muted hover:text-ink">
          <Info size={16} strokeWidth={1.5} aria-hidden />
        </button>
        <span role="tooltip" className="pointer-events-none absolute bottom-full right-0 z-20 mb-1 hidden w-max max-w-[16rem] rounded-md border border-line-strong bg-surface px-2.5 py-1.5 text-[12px] text-body-2 shadow-float group-focus-within:block group-hover:block">
          {VOICE_MESSAGES.unsupported}
        </span>
      </span>
    );
  }
  const { listening, state } = voice;
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <span role="status" aria-live="polite" data-testid="voice-status" className={cn("items-center gap-1.5 text-[13px] text-body-2", listening ? "inline-flex" : "sr-only")}>
        {listening ? (<><span className="h-2 w-2 rounded-full bg-accent motion-safe:animate-pulseSoft" aria-hidden />Listening…</>) : state === "error" ? "Voice input problem" : ""}
      </span>
      {/* a plain small icon, no bubble; on touch screens the tap area grows to 48 px (people wear gloves) without the icon changing */}
      <button type="button" onClick={voice.toggle} data-testid="mic-button" aria-pressed={listening}
        aria-label={listening ? `Stop ${label}` : `Start ${label}`}
        className={cn("flex h-7 w-7 shrink-0 items-center justify-center rounded-md transition-colors duration-150 [@media(pointer:coarse)]:h-12 [@media(pointer:coarse)]:w-12",
          listening || state === "error" ? "text-accent" : "text-muted hover:text-ink")}>
        {state === "error" ? <MicOff size={16} strokeWidth={1.6} aria-hidden /> : <Mic size={16} strokeWidth={listening ? 2.2 : 1.6} aria-hidden />}
      </button>
    </span>
  );
}

/** The inline messages: a clear error (mic blocked, page not secure, ...) and the privacy line until voice has been used once. */
export function VoiceNote({ voice, className }: { voice: SpeechInput; className?: string }) {
  if (!voice.supported) return null;
  return (
    <div className={cn("space-y-1", className)}>
      {voice.message && (
        <p role="alert" data-testid="voice-error" className="flex items-start gap-2 text-[13px] text-accent">
          <span className="min-w-0 flex-1">{voice.message}</span>
          <button type="button" onClick={voice.dismissError} className="shrink-0 underline underline-offset-2">Dismiss</button>
        </p>
      )}
      {(voice.firstUse || voice.listening) && <p data-testid="voice-privacy" className="text-[12px] text-muted">{PRIVACY_NOTE}</p>}
    </div>
  );
}
