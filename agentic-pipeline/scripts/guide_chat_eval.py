"""Small live evaluation of the conversational Guide (internal check, NOT an accuracy benchmark).

Runs scripted multi-turn conversations on Class 14 and Class 17 against the real model (BULLSAI_MODEL), with isolated state (no saved
sessions, no question log, no flags). An independent judge (openai/gpt-oss-120b through BullsAI) then assesses, separately,
 (a) factual support: is every claim in the reply supported by the exact slide text supplied?
 (b) conversation/progress: did the reply and the state change follow what the turn called for?
Output: reports/guide_chat_eval_2026-10-20.md and .json. Stops if the gateway fails twice in a row.

  .venv/bin/python scripts/guide_chat_eval.py
"""
import copy
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import llm  # noqa: E402
from src.ingest import guides as G  # noqa: E402
from src.modes import guide_chat as C  # noqa: E402
from src.modes import guide_slides as GS  # noqa: E402

JUDGE_MODEL = "openai/gpt-oss-120b"
SCRIPTS = {
    "Class 14": [
        ("@start", "Introduce ONLY the first instruction slide; ask one focused question; no later steps."),
        ("RESET", ""),
        ("I've reflected gluteus maximus", "Join midway: find the matching slide, briefly check earlier work from the guide, point to what comes next. Not claim the dissection is correct."),
        ("I didn't do the skin incision", "Treat an earlier step as not done: offer to go back to the incision step; do not advance."),
        ("yes", "Go back to that earlier step and present it."),
        ("ok I finished that, ready for the next one", "Self-reported completion plus a request to continue: move forward one step."),
        ("slide 5", "Navigate to slide 5."),
        ("Which muscle is visible superior to gluteus maximus?", "Answer from the guide without moving."),
        ("I see a big yellow thing and I think it's the liver", "Vague or wrong observation: do not confirm it; say it does not match the guide; restate what the guide asks them to find; do not invent."),
        ("Actually I meant slide 9", "Correct the location to slide 9."),
    ],
    "Class 17": [
        ("@start", "Introduce ONLY the first instruction slide; ask one focused question."),
        ("RESET", ""),
        ("I'm at the knee joint", "Either resolve to a slide about the knee joint or ask a short clarifying question listing the candidate slides."),
        ("slide 12", "Join at slide 12; recap earlier slides from the guide as a check question."),
        ("I haven't removed the posterior wall of the joint capsule", "Earlier step not done: offer to go back to that step."),
        ("yes", "Go back to that step and present it."),
        ("done, next", "Self-reported completion plus continue: move forward one step."),
        ("slide 13", "Navigate to slide 13 (first part)."),
        ("What is the anterior drawer sign?", "Answer from the guide text only, without moving."),
        ("the knee moves a bit I guess", "Vague observation: do not confirm; restate what the guide asks them to find."),
        ("Actually I'm at slide 17", "Correct the location to slide 17."),
    ],
}

JUDGE_FACT = """You are a strict independent checker. You get SOURCE slide text from a dissection guide and an ASSISTANT reply to a student.
Decide whether every factual or procedural claim in the reply is supported by the SOURCE text (paraphrase is fine; restating what the
student said is fine; questions are fine). List unsupported claims verbatim. Verdict: supported | minor_unsupported | unsupported.
JSON: {"verdict": "...", "unsupported": ["..."], "note": "short"}"""
JUDGE_CONV = """You are a strict independent checker of conversation behaviour for a lab-guide assistant. The STUDENT said something; the app
state before/after and the ASSISTANT reply are given, with what the turn SHOULD do. Judge only behaviour: did the reply and the position
change follow the expectation (position, no unwanted advance, one focused question at most, no claim that the dissection is "correct")?
Verdict: good | partly | poor. JSON: {"verdict": "...", "note": "short"}"""
FACT_SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string"}, "unsupported": {"type": "array", "items": {"type": "string"}},
                                                  "note": {"type": "string"}}, "required": ["verdict", "unsupported", "note"]}
CONV_SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string"}, "note": {"type": "string"}}, "required": ["verdict", "note"]}


def main():
    client, model = llm.make_client(), llm.default_model()
    m = G.map_by_file()
    out, fails = [], 0
    for label, script in SCRIPTS.items():
        entry = next(e for e in m.values() if e["class_label"] == label)
        steps = C.build_steps(GS.slides_of(entry["file"]), label)
        by = {s["id"]: s for s in steps}
        chat = C.GuideChat(entry, steps, client, model)
        st = C.new_state(entry)
        for text, expect in script:
            if text == "RESET":
                st = C.new_state(entry)
                continue
            before = {k: copy.deepcopy(st[k]) for k in ("pos", "done", "missing", "pending")}
            t0 = time.time()
            r = chat.handle(st, action=text[1:]) if text.startswith("@") else chat.handle(st, text)
            row = {"guide": label, "student": text, "expect": expect, "ok": r.ok, "seconds": round(time.time() - t0, 1), "before": before}
            if r.ok:
                fails = 0
                st = r.state
                msg = r.message
                row.update(reply=msg["text"], kind=msg["kind"], cites=msg["cites"], fallback=bool(msg.get("fallback")),
                           after={k: copy.deepcopy(st[k]) for k in ("pos", "done", "missing", "pending")})
            else:
                fails += 1
                row["error"] = r.error
                if fails >= 2:
                    print("Stopping: two failures in a row")
                    out.append(row)
                    return finish(out)
            out.append(row)
            print(f"[{label}] {text!r} -> ok={r.ok} pos={st['pos']} ({row['seconds']}s)")
    finish(out, steps_by_guide=None)


def source_for(row, by):
    ids = row.get("cites") or []
    return "\n\n".join(f"[slide {by[i]['slide']}] {by[i]['text']}" for i in ids if i in by)


def finish(rows, steps_by_guide=None):
    client = llm.make_client()
    m = G.map_by_file()
    cache = {}
    bad = 0
    for row in rows:
        if not row["ok"] or bad >= 2:
            continue
        label = row["guide"]
        if label not in cache:
            e = next(e for e in m.values() if e["class_label"] == label)
            cache[label] = {s["id"]: s for s in C.build_steps(GS.slides_of(e["file"]), label)}
        by = cache[label]
        src = source_for(row, by)
        try:
            if row["kind"] in ("clarify", "no_match", "which_missing", "return_offer", "no_slide", "at_first", "finished", "stay", "other",
                               "uncertain", "unexpected", "start_needed", "what_next"):
                row["fact"] = {"verdict": "n/a (standard wording)", "unsupported": [], "note": "template reply"}
            else:
                u = f"<SOURCE>\n{src}\n</SOURCE>\n<ASSISTANT>\n{row['reply']}\n</ASSISTANT>\n<STUDENT>\n{row['student']}\n</STUDENT>"
                row["fact"], _ = llm.complete_json(client, JUDGE_FACT, [{"role": "user", "content": u}], 1500, FACT_SCHEMA, JUDGE_MODEL)
            u = (f"<STUDENT>{row['student']}</STUDENT>\n<SHOULD>{row['expect']}</SHOULD>\n<STATE_BEFORE>{json.dumps(row['before'])}</STATE_BEFORE>\n"
                 f"<STATE_AFTER>{json.dumps(row['after'])}</STATE_AFTER>\n<ASSISTANT>\n{row['reply']}\n</ASSISTANT>")
            row["conv"], _ = llm.complete_json(client, JUDGE_CONV, [{"role": "user", "content": u}], 1500, CONV_SCHEMA, JUDGE_MODEL)
            bad = 0
        except llm.LLMError as exc:
            bad += 1
            row["judge_error"] = str(exc)[:120]
    write(rows)


def write(rows):
    (ROOT / "reports" / "guide_chat_eval_2026-10-20.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    lines = ["# Conversational Guide: live evaluation (2026-10-20)", "",
             f"Generation: {llm.default_model()} through BullsAI. Judge: {JUDGE_MODEL} through BullsAI. Isolated run: no saved sessions, no question log, no flags.",
             "This is a small internal check (two guides, scripted turns). It is not an accuracy benchmark, not medical validation, and the judge is another model.", ""]
    for r in rows:
        lines += [f"## {r['guide']}: {r['student']}", f"- should: {r['expect'] or '-'}", f"- ok: {r['ok']} ({r['seconds']} s)"]
        if not r["ok"]:
            lines += [f"- error: {r.get('error')}", ""]
            continue
        lines += [f"- state: {json.dumps(r['before'])} -> {json.dumps(r['after'])}", f"- kind: {r['kind']}, cites: {r['cites']}, fallback: {r['fallback']}",
                  "", "> " + r["reply"].replace("\n", "\n> "), "",
                  f"- judge, factual support: {(r.get('fact') or {}).get('verdict', '-')}; {(r.get('fact') or {}).get('note', '')}; unsupported: {(r.get('fact') or {}).get('unsupported', [])}",
                  f"- judge, conversation: {(r.get('conv') or {}).get('verdict', '-')}; {(r.get('conv') or {}).get('note', '')}"]
        if r.get("judge_error"):
            lines.append(f"- judge error: {r['judge_error']}")
        lines.append("")
    (ROOT / "reports" / "guide_chat_eval_2026-10-20.md").write_text("\n".join(lines), encoding="utf-8")
    print("written")


if __name__ == "__main__":
    main()
