"""Benchmark Quiz generation with real models on an ISOLATED store: cold builds, then reuse. Nothing real is touched.

  .venv/bin/python scripts/quiz_benchmark.py STORE_PATH CASE[,CASE...]
CASES: l02_cold5 l02_again5 l09_cold5 l09_again5 l02_cold10 l02_ten_after5 ...  (see CASES). Prints one JSON line per case and the accepted items.
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

L02, L09 = "Lecture 02 - Muscles of the Back", "Lecture 09 - The Hand"
L06 = "Lecture 06 - The Brachium"
CASES = {
    "l02_5": {"mode": "materials", "n": 5, "selected": [L02]},
    "l02_10": {"mode": "materials", "n": 10, "selected": [L02]},
    "l06_5": {"mode": "materials", "n": 5, "selected": [L06]},
    "l06_10": {"mode": "materials", "n": 10, "selected": [L06]},
    "l09_5": {"mode": "materials", "n": 5, "selected": [L09]},
    "l09_10": {"mode": "materials", "n": 10, "selected": [L09]},
}


def main():
    store = QuizStore(sys.argv[1])
    rt = service.build_runtime(warm=False)
    from app.data import lectures
    from src.ingest import guides
    allowed = [l["title"] for l in lectures()] + [g for g, _ in guides.guide_labels()]
    for name in sys.argv[2].split(","):
        t0 = time.time()
        out = qs.new_quiz("bench", allowed, CASES[name], rt, store=store, rng=random.Random())
        run = store.runs()[0]
        print(json.dumps({"case": name, "status": out["status"], "reason": out.get("reason"), "have": out["have"], "reused": out.get("reused"),
                          "generated": out.get("generated"), "seconds": round(time.time() - t0, 1), "calls": run.get("calls", 0),
                          "drafts": run.get("drafts", 0), "rejected_by_stage": run.get("rejected_by_stage", {}), "passages": run.get("passages"), "backend": run.get("backend"), "models": run.get("models"), "cost_usd": run.get("cost_usd")}), flush=True)
        for r in run.get("rejected") or []:
            print("   rejected", r["stage"], r["anchor"], r["reason"][:170], flush=True)
    print("ITEMS")
    for it in store.list_items(limit=40):
        print("ITEM", it["item_id"], "|", it["lead_in"])
        for o in it["options"]:
            print("    ", o["id"], o["text"], "<-- KEY" if o["id"] in it["answer_ids"] else "")
        print("     why:", it["explanation"][:160])


if __name__ == "__main__":
    main()
