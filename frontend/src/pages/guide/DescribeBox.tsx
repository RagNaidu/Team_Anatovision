import { useRef } from "react";
import { Button } from "@/components/ui/button";
import { useSpeechInput } from "@/hooks/useSpeechInput";
import { MicButton, VoiceNote } from "@/components/voice/Voice";

const MAX = 1000;

/** "Describe what you see or what you did": typed or dictated. Dictation fills the box; only Check submits it. */
export function DescribeBox({ text, loading, onChange, onCheck }: { text: string; loading: boolean; onChange: (t: string) => void; onCheck: (text: string) => void }) {
  const textRef = useRef(text); textRef.current = text;
  const voice = useSpeechInput({ getText: () => textRef.current, onText: onChange, maxLength: MAX });
  return (
    <>
      <label htmlFor="describe" className="serif-label mb-2 block !text-[15px]">Describe what you see or what you did</label>
      <div className="rounded-xl border border-line-strong bg-surface p-3 shadow-soft">
        <textarea id="describe" rows={3} value={text} maxLength={MAX} disabled={loading}
          onChange={(e) => { voice.userEdited(); onChange(e.target.value); }}
          placeholder="For example: I found the great saphenous vein near the saphenous opening."
          className="block w-full resize-y bg-transparent px-1.5 py-1 text-[15px] outline-none placeholder:text-muted" />
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <span className="text-[12px] tabular-nums text-muted">{text.length} / {MAX}</span>
          <div className="flex flex-wrap items-center justify-end gap-3">
            <MicButton voice={voice} label="voice input for your description" />
            <Button onClick={() => { voice.finish(); onCheck(text.trim()); }} disabled={!text.trim() || loading}>Check</Button>
          </div>
        </div>
        <VoiceNote voice={voice} className="mt-2" />
      </div>
    </>
  );
}
