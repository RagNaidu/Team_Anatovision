"""Run questions through the REAL pipeline (BullsAI + the real index) without touching any log.

No-logging method: service.ask(log=False), and flags/question-log/settings paths pointed at a temp folder, so
data/flags.jsonl, data/question_log.jsonl and data/verified_fixes.jsonl are never written.

  .venv/bin/python scripts/live_ask.py "apex" "What is the circle of Willis?"   [--student <lecture titles separated by |>] [--web on|off]
"""
import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def sandbox():
    from src import usage, verified
    from src.modes import qa
    tmp = Path(tempfile.mkdtemp(prefix="anato_live_"))
    qa.FLAGS_PATH = tmp / "flags.jsonl"
    verified.FLAGS_PATH = tmp / "flags.jsonl"
    usage.QUESTION_LOG_PATH = tmp / "qlog.jsonl"
    usage.SETTINGS_PATH = tmp / "settings.json"
    return tmp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("questions", nargs="+")
    ap.add_argument("--student", default=None, help="lecture titles the student may open, separated by |")
    ap.add_argument("--web", default=None)
    a = ap.parse_args()
    if a.web:
        os.environ["WEB_FALLBACK"] = a.web
    sandbox()
    from src import service
    rt = service.build_runtime()
    allowed = None if a.student is None else [x for x in a.student.split("|") if x]
    for q in a.questions:
        t = time.perf_counter()
        r = service.ask(q, "", True, allowed, runtime=rt, log=False)
        print("=" * 90, f"\nQ: {q}\n{round(time.perf_counter() - t, 1)}s status={r['status']} mode={r['mode']} tier={r['tier']} reason={r['reason']}")
        print(r["answer_text"])
        print("citations:", [(c["n"], c["cite"], c["matched"]) for c in r["citations"]])


if __name__ == "__main__":
    main()
