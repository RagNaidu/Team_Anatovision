import { useRef, useState } from "react";
import { useSpeechInput } from "@/hooks/useSpeechInput";
import { MicButton, VoiceNote } from "@/components/voice/Voice";
import { parseQuizPhrase } from "@/lib/speech/quizCommands";
import type { Interpret } from "@/lib/speech/controller";

interface Props {
  options: string[];
  /** a letter that was heard but not confirmed yet: it is shown, never saved */
  pending: string | null;
  onPending: (id: string | null) => void;
  chosen: string[];
  questionNo: number;
  /** save the answer (the same call a tap makes) */
  onConfirm: (id: string) => Promise<void> | void;
  onNext: () => void;
}

/**
 * Answer by voice, while the mic is on: "A".."D" (or "option b") marks a choice, "submit" confirms it, "next" moves on.
 * A heard letter is only marked (dashed outline) until "submit": nothing is saved on a mishearing, and a tap on any option fixes it.
 * What was heard is always shown. Nothing is heard until the person taps the mic.
 */
export function QuizVoice({ options, pending, onPending, chosen, questionNo, onConfirm, onNext }: Props) {
  const [heard, setHeard] = useState("");
  const [note, setNote] = useState<string | null>(null);
  const pend = useRef(pending); pend.current = pending;
  const setPend = (v: string | null) => { pend.current = v; onPending(v); };

  const interpret: Interpret = (phrase) => {
    const p = parseQuizPhrase(phrase);
    setHeard(p.heard);
    if (p.ignored) {
      setNote(p.reason === "several-letters" ? "I heard more than one letter. Say just one: A, B, C or D." : "That wasn't an answer command. Say A, B, C or D, then “submit”.");
      return { keep: "" };
    }
    for (const c of p.commands) {
      if (c.kind === "pick") {
        if (!options.includes(c.letter)) { setNote(`There is no option ${c.letter} on this question.`); continue; }
        setPend(c.letter);
        setNote(`Heard ${c.letter}. Say “submit” to save it, or tap the answer you meant.`);
      } else if (c.kind === "submit") {
        const id = pend.current;
        if (id) { setPend(null); void onConfirm(id); setNote(`Saved ${id}. Say “next” to continue.`); }
        else if (chosen.length) setNote(`${chosen[0]} is already saved. Say “next” to continue.`);
        else setNote("Say A, B, C or D first, then “submit”.");
      } else if (pend.current) {
        setNote(`Say “submit” to save ${pend.current} first, or tap another answer.`);
      } else { setNote(null); onNext(); }
    }
    return { keep: "" };
  };

  const voice = useSpeechInput({
    getText: () => "",
    onText: (t) => { if (t) setHeard(t); },      // the phrase still being spoken, live; finished phrases are shown by interpret()
    interpret, silenceMs: 10_000,   // longer than for dictation: the next question has to be read between commands
  });

  return (
    <div className="mt-5 rounded-xl border border-line bg-surface-2 px-4 py-3" aria-label="Answer by voice" data-testid="quiz-voice">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0 text-[13px] text-body-2">
          Tap the mic, then say <b className="font-semibold">A</b>, <b className="font-semibold">B</b>, <b className="font-semibold">C</b> or <b className="font-semibold">D</b>, then <b className="font-semibold">“submit”</b>. Say <b className="font-semibold">“next”</b> to move on.
        </div>
        <MicButton voice={voice} label={`voice answers for question ${questionNo}`} />
      </div>
      {voice.supported && (
        <div role="status" aria-live="polite" data-testid="quiz-heard" className="mt-2 min-h-[20px] text-[13px]">
          {heard && <p><span className="text-muted">Heard:</span> <span className="font-medium text-ink">“{heard}”</span></p>}
          {note && <p className="text-body-2">{note}</p>}
        </div>
      )}
      <VoiceNote voice={voice} className="mt-1" />
    </div>
  );
}
