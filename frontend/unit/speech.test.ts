// Run: npm run test:unit   (node's built-in test runner, no extra dependency)
import test from "node:test";
import assert from "node:assert/strict";
import { SpeechController, recognitionCtor, joinText, VOICE_MESSAGES, type ControllerOptions, type RecognitionLike, type SpeechEventLike } from "../src/lib/speech/controller.ts";
import { parseQuizPhrase } from "../src/lib/speech/quizCommands.ts";

/** A hand-driven SpeechRecognition: the test says what the "person" said. */
class FakeRec implements RecognitionLike {
  static last: FakeRec | null = null;
  static throwOnStart = false;
  lang = ""; continuous = false; interimResults = false; maxAlternatives = 0;
  onresult: RecognitionLike["onresult"] = null; onerror: RecognitionLike["onerror"] = null; onend: RecognitionLike["onend"] = null;
  started = false; stopped = false; aborted = false;
  constructor() { FakeRec.last = this; }
  start() { if (FakeRec.throwOnStart) throw new Error("already started"); this.started = true; }
  stop() { this.stopped = true; queueMicrotask(() => this.onend?.()); }   // like a real engine: stop() ends with onend
  abort() { this.aborted = true; }
  /** the results so far (cumulative, like Chrome in continuous mode) */
  say(items: Array<[string, boolean]>) {
    const results = items.map(([t, final]) => Object.assign([{ transcript: t }], { isFinal: final }));
    this.onresult?.({ resultIndex: 0, results: Object.assign(results, { length: results.length }) } as unknown as SpeechEventLike);
  }
  fail(code: string) { this.onerror?.({ error: code }); this.onend?.(); }
}

function clock() {
  let now = 0; let id = 0; const q = new Map<number, { at: number; fn: () => void }>();
  return {
    set: (fn: () => void, ms: number) => { id++; q.set(id, { at: now + ms, fn }); return id; },
    clear: (h: unknown) => { q.delete(h as number); },
    advance(ms: number) { const end = now + ms; for (;;) { const next = [...q.entries()].filter(([, v]) => v.at <= end).sort((a, b) => a[1].at - b[1].at)[0]; if (!next) break; now = next[1].at; q.delete(next[0]); next[1].fn(); } now = end; },
  };
}

type Over = Partial<ControllerOptions> & { box?: { text: string } };
function make(over: Over = {}) {
  const box = over.box ?? { text: "" };
  const c = clock();
  const states: string[] = [];
  const ctl = new SpeechController({
    ctor: FakeRec as never, getText: () => box.text, onText: (t) => { box.text = t; },
    onState: (s, e) => states.push(e ? `${s}:${e}` : s), timers: c, secure: () => true, ...over,
  });
  return { ctl, box, c, states, rec: () => FakeRec.last! };
}

test("interim words show live and the final phrase replaces them", () => {
  const { ctl, box, rec } = make();
  assert.equal(ctl.start(), true);
  assert.equal(rec().lang, "en-US"); assert.equal(rec().continuous, true); assert.equal(rec().interimResults, true);
  rec().say([["what is the fem", false]]);
  assert.equal(box.text, "what is the fem");
  rec().say([["what is the femoral triangle", true]]);
  assert.equal(box.text, "what is the femoral triangle");
  rec().say([["what is the femoral triangle", true], ["and its", false]]);
  assert.equal(box.text, "what is the femoral triangle and its");
});

test("dictation is appended to what is already in the box, never overwrites it", () => {
  const { ctl, box, rec } = make({ box: { text: "Femoral triangle:" } });
  ctl.start();
  rec().say([["borders", false]]);
  assert.equal(box.text, "Femoral triangle: borders");
  rec().say([["borders", true]]);
  assert.equal(box.text, "Femoral triangle: borders");
  assert.equal(joinText("a ", " b"), "a b");
});

test("it stops by itself after about 3 seconds of silence (and nothing is sent)", async () => {
  const { ctl, c, states, rec } = make();
  ctl.start();
  rec().say([["hello", true]]);
  c.advance(2900);
  assert.equal(ctl.listening, true);
  c.advance(200);
  assert.equal(rec().stopped, true);
  await Promise.resolve();
  assert.equal(ctl.state, "idle"); assert.deepEqual(states, ["listening", "idle"]);
});

test("speaking again restarts the silence timer", () => {
  const { ctl, c, rec } = make();
  ctl.start();
  rec().say([["one", false]]); c.advance(2500);
  rec().say([["one two", false]]); c.advance(2500);
  assert.equal(rec().stopped, false);
  c.advance(600);
  assert.equal(rec().stopped, true);
});

test("before anyone speaks there is a longer grace period, then it stops", () => {
  const { ctl, c, rec } = make();
  ctl.start();
  c.advance(5900); assert.equal(rec().stopped, false);
  c.advance(200); assert.equal(rec().stopped, true);
  assert.equal(ctl.wasHeard, false);
});

test("tap again stops", async () => {
  const { ctl, rec } = make();
  ctl.toggle(); assert.equal(ctl.listening, true);
  ctl.toggle(); assert.equal(rec().stopped, true);
  await Promise.resolve(); assert.equal(ctl.state, "idle");
});

test("unsupported browser: no recognition, state says so, nothing throws", () => {
  const { ctl, states } = make({ ctor: null });
  assert.equal(ctl.supported, false);
  assert.equal(ctl.start(), false);
  assert.deepEqual(states, ["error:unsupported"]);
  assert.equal(VOICE_MESSAGES.unsupported, "Voice input works in Chrome, Edge and Safari");
  assert.equal(recognitionCtor({}), null);
  assert.equal(recognitionCtor({ webkitSpeechRecognition: FakeRec as never }), FakeRec);
  assert.equal(recognitionCtor({ SpeechRecognition: FakeRec as never }), FakeRec);
});

test("microphone permission denied gives a clear error and no text", () => {
  const { ctl, box, states, rec } = make();
  ctl.start();
  rec().fail("not-allowed");
  assert.deepEqual(states, ["listening", "error:denied"]);
  assert.equal(ctl.error, "denied");
  assert.equal(box.text, "");
  assert.match(VOICE_MESSAGES.denied, /microphone is blocked/i);
  ctl.clearError(); assert.equal(ctl.state, "idle");
  const again = make(); again.ctl.start(); again.rec().fail("service-not-allowed"); assert.equal(again.ctl.error, "denied");
});

test("a page that is not https or localhost explains why and never starts", () => {
  FakeRec.last = null;
  const { ctl, states } = make({ secure: () => false });
  assert.equal(ctl.start(), false);
  assert.equal(FakeRec.last, null, "no recognition object was even created");
  assert.deepEqual(states, ["error:insecure"]);
  assert.match(VOICE_MESSAGES.insecure, /https or localhost/);
});

test("other engine errors map to readable kinds", () => {
  for (const [code, kind] of [["no-speech", "no-speech"], ["audio-capture", "no-mic"], ["network", "network"], ["weird", "other"]] as const) {
    const m = make(); m.ctl.start(); m.rec().fail(code); assert.equal(m.ctl.error, kind, code);
  }
  const m = make(); m.ctl.start(); m.rec().onerror?.({ error: "aborted" }); assert.equal(m.ctl.state, "listening", "aborted is our own stop, not a fault");
});

test("a start that throws becomes an error, not a crash", () => {
  FakeRec.throwOnStart = true;
  try { const { ctl } = make(); assert.equal(ctl.start(), false); assert.equal(ctl.error, "other"); } finally { FakeRec.throwOnStart = false; }
});

test('the word "send" is only text: dictation never sends or strips anything', () => {
  const { ctl, box, rec } = make();
  ctl.start();
  rec().say([["please send it", true]]);
  assert.equal(box.text, "please send it");
});

test("spoken commands (the quiz): only finished phrases are interpreted, once, and the words are not added to the text", () => {
  const seen: string[] = []; const acted: string[] = [];
  const { ctl, box, rec } = make({ interpret: (p) => { seen.push(p); return { keep: "", action: () => acted.push(p) }; } });
  ctl.start();
  rec().say([["option b", false]]);
  assert.deepEqual(seen, [], "an interim phrase is never a command");
  assert.equal(box.text, "option b", "but it is shown while it is being spoken");
  rec().say([["option b", true]]);
  rec().say([["option b", true], ["submit", false]]);
  rec().say([["option b", true], ["submit", true]]);
  assert.deepEqual(seen, ["option b", "submit"], "each phrase once");
  assert.deepEqual(acted, ["option b", "submit"]);
  assert.equal(box.text, "");
});

test("finish (the text was sent or typed over) ignores words that still arrive", async () => {
  const { ctl, box, rec } = make();
  ctl.start(); rec().say([["hello", false]]);
  ctl.finish(); box.text = "";
  rec().say([["hello there", true]]);
  assert.equal(box.text, "", "late results never refill the box");
  await Promise.resolve(); assert.equal(ctl.state, "idle");
});

test("maxLength clips dictated text", () => {
  const { ctl, box, rec } = make({ maxLength: 10 });
  ctl.start(); rec().say([["abcdefghijklmnop", true]]);
  assert.equal(box.text, "abcdefghij");
});

test("abort (leaving the page) detaches handlers and stops the engine", () => {
  const { ctl, rec } = make();
  ctl.start(); const r = rec(); ctl.abort();
  assert.equal(r.aborted, true); assert.equal(r.onresult, null); assert.equal(ctl.state, "idle");
});

test("quiz phrases: letters, option b, submit, next; unknown talk is ignored whole", () => {
  const cmds = (s: string) => { const p = parseQuizPhrase(s); return p.ignored ? null : p.commands.map((c) => (c.kind === "pick" ? c.letter : c.kind)).join(","); };
  assert.equal(cmds("B"), "B"); assert.equal(cmds("b."), "B"); assert.equal(cmds("Option C"), "C"); assert.equal(cmds("option d."), "D");
  assert.equal(cmds("answer a"), "A"); assert.equal(cmds("bee"), "B"); assert.equal(cmds("sea"), "C");
  assert.equal(cmds("submit"), "submit"); assert.equal(cmds("Submit answer"), "submit"); assert.equal(cmds("confirm"), "submit");
  assert.equal(cmds("next"), "next"); assert.equal(cmds("next question"), "next");
  assert.equal(cmds("b submit"), "B,submit");
  assert.equal(parseQuizPhrase("the femoral nerve").ignored, true);
  assert.equal(parseQuizPhrase("I think it is b").ignored, true);
  assert.equal(parseQuizPhrase("a b").reason, "several-letters");
  assert.equal(parseQuizPhrase("e").ignored, true);
  assert.equal(parseQuizPhrase(" Option B ").heard, "Option B");
});
