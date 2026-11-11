import { useRef } from "react";
import { useSpeechInput } from "@/hooks/useSpeechInput";
import { MicButton, VoiceNote } from "@/components/voice/Voice";

export const TOPIC_MAX = 80;

/** The quiz topic field, typed or dictated (the mic sits inside the field, on the right). Dictation never starts the quiz: "Build quiz" is a separate press. */
export function TopicInput({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  const ref = useRef(value); ref.current = value;
  const voice = useSpeechInput({ getText: () => ref.current, onText: onChange, maxLength: TOPIC_MAX });
  return (
    <div>
      <label htmlFor="topic" className="serif-label mb-1.5 block !text-[15px]">Topic</label>
      <div className="relative">
        <input id="topic" value={value} maxLength={TOPIC_MAX} onChange={(e) => { voice.userEdited(); onChange(e.target.value); }} placeholder="For example: rotator cuff muscles"
          className="h-11 w-full rounded-lg border border-line-strong bg-surface pl-3 pr-11 text-[15px]" />
        <MicButton voice={voice} label="voice input for the topic" className="absolute right-1.5 top-1/2 -translate-y-1/2" />
      </div>
      <VoiceNote voice={voice} className="mt-1" />
    </div>
  );
}
