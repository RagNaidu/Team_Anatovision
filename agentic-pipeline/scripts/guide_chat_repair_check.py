"""Isolated multi-turn check of the repaired Guide (real model, no storage): after every turn, the saved position, the header text, the
location wording and the cited slides must agree. Output: reports/guide_chat_repair_check_2026-10-20.md. Exit 1 on any contradiction."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import llm  # noqa: E402
from src.ingest import guides as G  # noqa: E402
from src.modes import guide_chat as C  # noqa: E402
from src.modes import guide_slides as GS  # noqa: E402

SCRIPTS = {
    "Class 14": ["@start", "yes", "yes", "done", "yes", "RESET", "slide 7", "yes", "what does slide 9 cover?", "yes", "what are the borders of gluteus maximus?",
                 "yes", "I didn't do the one you just asked about", "yes", "next"],
    "Class 17": ["@start", "yes", "what is slide 13 about?", "yes", "done", "next", "RESET", "I've reflected the skin and capsule on slide 11, done",
                 "yes", "no", "no", "yes"],
}
CLAIM = re.compile(r"\b(?:you(?:'re| are)|we(?:'re| are)|still|currently|now)\b[^.?!\n]{0,25}?\b(?:on|at)\s+slides?\s+(\d+)", re.I)


def main():
    client, model = llm.make_client(), llm.default_model()
    lines = [f"# Repair check, isolated multi-turn ({model} through BullsAI)", "",
             "Invariant per turn: header slide (from the saved state) = every 'you are on/at slide N' in the reply; cites are listed; no saved storage.", ""]
    bad = 0
    m = G.map_by_file()
    for label, script in SCRIPTS.items():
        e = next(e for e in m.values() if e["class_label"] == label)
        steps = C.build_steps(GS.slides_of(e["file"]), label)
        by = {s["id"]: s for s in steps}
        chat, st = C.GuideChat(e, steps, client, model), C.new_state(e)
        lines.append(f"## {label}")
        fails = 0
        for t in script:
            if t == "RESET":
                st = C.new_state(e)
                lines.append("*(new session)*")
                continue
            r = chat.handle(st, action=t[1:]) if t.startswith("@") else chat.handle(st, t)
            if not r.ok:
                fails += 1
                lines.append(f"- **{t}** -> FAILED: {r.error}")
                if fails >= 2:
                    break
                continue
            fails, st = 0, r.state
            v = C.view(st, steps)
            msg = r.message
            issues = [f"reply says slide {x} but header says {v['slide']}" for x in CLAIM.findall(msg["text"]) if int(x) != v["slide"]]
            bad += len(issues)
            lines += [f"- **{t}** -> header: slide {v['slide']} (step {v['position']}/{v['total']}), done {[by[i]['slide'] for i in st['done']]}, "
                      f"missing {[by[i]['slide'] for i in st['missing']]}, asked {(st['asked'] or {}).get('type')}, pending {(st['pending'] or {}).get('type')}, "
                      f"kind {msg['kind']}, cites {[by[c]['slide'] for c in msg['cites']]}" + (f"  **CONTRADICTION: {issues}**" if issues else ""),
                      "  > " + msg["text"].replace("\n", "\n  > ")]
            print(label, t, "->", v["slide"], msg["kind"], "OK" if not issues else issues)
        lines.append("")
    lines.append(f"Contradictions found: {bad}")
    (ROOT / "reports" / "guide_chat_repair_check_2026-10-20.md").write_text("\n".join(lines), encoding="utf-8")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
