"""Time the stages of POST /api/ask for 8 questions against the sandbox server (scripts/api_sandbox.py, which sets API_TIMING_LOG).

    SANDBOX_DIR=/tmp/anatovision-sandbox .venv/bin/python scripts/api_timing.py [--label before] [--clear-web-cache]

Prints one table (seconds per stage; `retrieval` = search minus rerank) and writes reports/api_timing_<label>.json. Nothing goes to real data files.
"""
import argparse
import json
import os
import shutil
import statistics
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = [("femoral triangle (brief)", "What are the boundaries and contents of the femoral triangle?", "brief"),
             ("femoral triangle (detailed)", "What are the boundaries and contents of the femoral triangle?", "detailed"),
             ("apex (term)", "apex", "brief"),
             ("procedural guide", "How do I dissect the gluteal region?", "brief"),
             ("wikipedia", "What is Broca's area?", "brief"),
             ("amoxicillin", "What dose of amoxicillin should I take for a sore throat?", "brief"),
             ("notes: deltoid nerve", "What nerve supplies the deltoid muscle?", "brief"),
             ("notes: middle ear walls", "What are the walls of the middle ear?", "brief")]
COLS = ("rewrite", "term_check", "retrieval", "rerank", "coverage_check", "scope_check", "web_lookup", "answer", "citations", "safe_layer")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--box", default=os.environ.get("SANDBOX_DIR", "/tmp/anatovision-sandbox"))
    ap.add_argument("--label", default="run")
    ap.add_argument("--clear-web-cache", action="store_true")
    a = ap.parse_args()
    box = Path(a.box)
    if a.clear_web_cache:
        shutil.rmtree(box / "web_cache", ignore_errors=True)
    log = box / "timing.jsonl"
    c = httpx.Client(base_url=a.base, timeout=300)
    assert c.post("/api/auth/login", json={"username": "student", "password": (box / "PASSWORD.txt").read_text().strip()}).status_code == 200
    rows = []
    for name, q, length in QUESTIONS:
        n0 = len(log.read_text().splitlines()) if log.exists() else 0
        chat = c.post("/api/chats").json()
        t0 = time.perf_counter()
        r = c.post("/api/ask", json={"chat_id": chat["id"], "question": q, "length": length})
        wall = time.perf_counter() - t0
        m = r.json()
        rec = json.loads(log.read_text().splitlines()[n0])
        by = {}
        for s in rec["stages"]:
            by[s["name"]] = by.get(s["name"], 0.0) + s["seconds"]
        by["retrieval"] = by.pop("search", 0.0) - by.get("rerank", 0.0)
        by["answer"] = by.get("answer", 0.0) + by.pop("answer_retry", 0.0) + by.pop("verbatim_fix", 0.0)
        rows.append({"name": name, "kind": m.get("kind"), "wall": wall, "server": rec["total"], "stages": by, "raw": rec["stages"],
                     "sources": [s["type"] for s in m.get("sources", [])], "markdown": m.get("markdown", "")})
    print(f"{'question':30} {'kind':12} " + " ".join(f"{c_[:9]:>9}" for c_ in COLS) + f" {'total':>7}")
    for r in rows:
        print(f"{r['name']:30} {r['kind']:12} " + " ".join(f"{r['stages'].get(c_, 0):9.2f}" for c_ in COLS) + f" {r['wall']:7.1f}")
    walls = [r["wall"] for r in rows]
    print(f"median total {statistics.median(walls):.1f} s, slowest {max(walls):.1f} s, sum {sum(walls):.0f} s")
    (ROOT / "reports" / f"api_timing_{a.label}.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
