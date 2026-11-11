"""Isolated live check of the Quiz pipeline (real Gemma generation + gpt-oss-120b verification). Storage is a temp file; nothing real is touched.

  .venv/bin/python scripts/quiz_live_check.py CASE [STORE_PATH]
CASE: materials5 | materials10 | topic5 | web5 | thin  (see CASES). Prints a JSON summary and the passing questions.
"""
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import service  # noqa: E402
from src.quiz import service as qs  # noqa: E402
from src.quiz.store import QuizStore  # noqa: E402

CASES = {
    "materials5": {"mode": "materials", "n": 5, "selected": ["Lecture 09 - The Hand"]},
    "materials10": {"mode": "materials", "n": 10, "selected": ["Lecture 09 - The Hand", "Lecture 11 - Gluteal Region and Posterior Thigh"]},
    "guide5": {"mode": "materials", "n": 5, "selected": ["Dissection Guide, Class 14"]},
    "topic5": {"mode": "topic", "n": 5, "topic": "rotator cuff"},
    "web5": {"mode": "topic", "n": 5, "topic": "cubital fossa", "allowed": []},          # a student with no grants: OpenStax has nothing on it, so Wikipedia is asked
    "web_pop": {"mode": "topic", "n": 5, "topic": "popliteal fossa", "allowed": []},
    "web_carotid": {"mode": "topic", "n": 5, "topic": "carotid triangle", "allowed": []},
    "web_cubital": {"mode": "topic", "n": 5, "topic": "cubital fossa", "allowed": []},
    "thin": {"mode": "topic", "n": 5, "topic": "ligament of Struthers", "allowed": []},   # an anatomy topic with too little approved source text
    "offtopic": {"mode": "topic", "n": 5, "topic": "xylophone orchestra tuning", "allowed": []},
}


def main():
    case = sys.argv[1]
    store = QuizStore(sys.argv[2] if len(sys.argv) > 2 else f"/tmp/never_used_{case}.db")
    rt = service.build_runtime(warm=False)
    from app.data import lectures  # noqa
    from src.ingest import guides
    allowed = CASES[case].get("allowed", [l["title"] for l in lectures()] + [g for g, _ in guides.guide_labels()])
    t0 = time.time()
    out = qs.new_quiz("live", allowed, {k: v for k, v in CASES[case].items() if k != "allowed"}, rt, store=store, rng=random.Random(7), progress=lambda a, b, note="": print("  ready", a, "of", b, note, flush=True))
    print(json.dumps({**out, "seconds": round(time.time() - t0, 1)}, indent=1))
    run = store.runs()[0]
    print("run:", json.dumps({k: run.get(k) for k in ("events", "web_used", "passages", "drafts", "calls", "passed", "rejected_by_stage")}, indent=1))
    for r in (run.get("rejected") or [])[:12]:
        print("  rejected", r["stage"], r["anchor"], r["reason"][:140])
    for it in store.list_items(limit=12):
        print("\nITEM", it["item_id"], it["tiers"], "|", it["lead_in"])
        for o in it["options"]:
            print("  ", o["id"], o["text"], "<-- KEY" if o["id"] in it["answer_ids"] else "")
        print("   explanation:", it["explanation"][:200])


if __name__ == "__main__":
    main()
