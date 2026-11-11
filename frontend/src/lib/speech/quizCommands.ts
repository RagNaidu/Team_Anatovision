/** Spoken quiz commands (hands-free only): "A".."D" or "option b" picks, "submit" confirms, "next" moves on. Pure, no browser needed. */
export type QuizCommand = { kind: "pick"; letter: "A" | "B" | "C" | "D" } | { kind: "submit" } | { kind: "next" };
export interface QuizParse { commands: QuizCommand[]; heard: string; ignored: boolean; reason?: "unknown" | "several-letters" }

// Speech engines write a spoken letter in many ways ("b", "B.", "bee"). Only these spellings count, and only as a whole word.
const LETTER: Record<string, QuizCommand & { kind: "pick" }> = {
  a: { kind: "pick", letter: "A" }, ay: { kind: "pick", letter: "A" },
  b: { kind: "pick", letter: "B" }, bee: { kind: "pick", letter: "B" }, be: { kind: "pick", letter: "B" },
  c: { kind: "pick", letter: "C" }, see: { kind: "pick", letter: "C" }, sea: { kind: "pick", letter: "C" },
  d: { kind: "pick", letter: "D" }, dee: { kind: "pick", letter: "D" },
};
const FILLER = new Set(["option", "choice", "answer", "letter", "number", "pick", "select", "choose"]);

/**
 * One finished phrase in, commands out. Anything that is not exactly a command is ignored whole (so talk in the lab can never change an answer),
 * and the phrase is still returned as `heard` so the screen can show what was understood.
 */
export function parseQuizPhrase(phrase: string): QuizParse {
  const heard = phrase.trim();
  const words = heard.toLowerCase().replace(/[.,!?;:"“”'’]/g, " ").split(/\s+/).filter(Boolean);
  const commands: QuizCommand[] = [];
  for (let i = 0; i < words.length; i++) {
    const w = words[i];
    if (FILLER.has(w) && i + 1 < words.length && LETTER[words[i + 1]]) { commands.push(LETTER[words[i + 1]]); i++; continue; }
    if (w === "confirm" || w === "submit") { commands.push({ kind: "submit" }); if (words[i + 1] === "answer") i++; continue; }
    if (w === "next") { commands.push({ kind: "next" }); if (words[i + 1] === "question") i++; continue; }
    if (LETTER[w]) { commands.push(LETTER[w]); continue; }
    return { commands: [], heard, ignored: true, reason: "unknown" };
  }
  if (!commands.length) return { commands: [], heard, ignored: true, reason: "unknown" };
  const letters = new Set(commands.filter((c) => c.kind === "pick").map((c) => (c as { letter: string }).letter));
  if (letters.size > 1) return { commands: [], heard, ignored: true, reason: "several-letters" };
  return { commands, heard, ignored: false };
}
