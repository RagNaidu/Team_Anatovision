"""Audit every lecture's quiz evidence, then optionally run real isolated 5/10-item builds.

  .venv/bin/python scripts/quiz_all_lectures_check.py
  .venv/bin/python scripts/quiz_all_lectures_check.py --live

No real student store is opened for writing. The JSON/Markdown reports distinguish
local evidence availability from a successful live quiz and stop live calls when
the shared gateway is unavailable. Re-run --live after connectivity is restored.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sqlite3
import sys
import tempfile
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import llm  # noqa: E402
from src.modes import qa  # noqa: E402
from src.quiz import evidence, items, service as quiz  # noqa: E402
from src.quiz.store import QuizStore  # noqa: E402

REPORT = ROOT / "reports" / "quiz_all_lectures_2026-10-20"
PROTECTED = ["flags.jsonl", "question_log.jsonl", "chats.db", "users.json",
             "guide_sessions.db", "verified_fixes.jsonl", "quizzes.db"]
MODELS = ["google/gemma-4-31B-it", "openai/gpt-oss-120b"]


def fingerprint(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def protected():
    return {name: fingerprint(ROOT / "data" / name) for name in PROTECTED}


class ReadOnlyBank:
    """Just the list_items interface needed to assess cache eligibility."""
    def list_items(self, status=None, limit=5000):
        path = ROOT / "data" / "quizzes.db"
        if not path.exists():
            return []
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
            db.row_factory = sqlite3.Row
            sql, args = "SELECT * FROM items", []
            if status:
                sql += " WHERE review_status = ?"
                args.append(status)
            rows = db.execute(sql + " ORDER BY created DESC LIMIT ?", (*args, limit))
            return [QuizStore._item(row) for row in rows]


def probe(client, model):
    start = time.perf_counter()
    try:
        reply = client.with_options(timeout=15, max_retries=0).chat.completions.create(
            model=model, max_tokens=100,
            messages=[{"role": "user", "content": "Reply with the single word OK."}])
        return {"model": model, "reachable": True,
                "has_text": bool(reply.choices[0].message.content),
                "seconds": round(time.perf_counter() - start, 1)}
    except Exception as exc:
        return {"model": model, "reachable": False,
                "seconds": round(time.perf_counter() - start, 1),
                "error_type": type(exc).__name__,
                "cause_type": type(exc.__cause__).__name__ if exc.__cause__ else None,
                "http_status": getattr(exc, "status_code", None)}


def write_report(report):
    REPORT.parent.mkdir(exist_ok=True)
    tmp = REPORT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(report, indent=2))
    tmp.replace(REPORT.with_suffix(".json"))
    lines = ["# All-lecture Quiz audit — 2026-10-20", "",
             f"Updated UTC: {report['updated_utc']}", "",
             "Local evidence checks are not successful live quizzes or factual accuracy validation.", "",
             f"Lecture files: **{len(report['lectures'])}**. Distinct files/titles are used because lecture numbers repeat.", "",
             "## Shared connection check", ""]
    if report.get("gateway"):
        for p in report["gateway"]:
            lines.append(f"- {p['model']}: {'reachable' if p['reachable'] else 'UNREACHABLE'}; "
                         f"{p['seconds']} s; {p.get('error_type', '')} {p.get('cause_type') or ''}.")
    else:
        lines.append("Live model calls were not requested for this run.")
    for p in report.get("gateway_after") or []:
        lines.append(f"- After the run, {p['model']}: {'reachable' if p['reachable'] else 'REFUSED, HTTP ' + str(p.get('http_status')) + ' ' + str(p.get('detail'))}.")
    if report.get("blocked_reason"):
        lines.extend(["", report["blocked_reason"]])
    lines.extend(["", "## Per-lecture results", "",
                  "Pool capacity is the existing heuristic, not a count of verified questions. Cached items are filtered by current version, sources, scope, and grants.", "",
                  "| Lecture | Usable passages | Usable words | Evidence 5/10 | Cached items eligible before the audit | Live 5 (cold) | Live 10 (after the 5) | Re-run 5 after fixes | Re-run 10 after fixes |",
                  "|---|---:|---:|---|---:|---|---|---|---|"])
    for row in report["lectures"]:
        cases = row.get("live", {})
        def label(n):
            c = cases.get(str(n))
            if not c:
                return "Not run"
            if c["status"] == "blocked":
                return "Blocked: " + (c.get("reason") or "gateway")[:70]
            tail = ""
            if c.get("rejected_by_stage"):
                tail = "; rejected " + ", ".join(f"{k} {v}" for k, v in c["rejected_by_stage"].items())
            why = f"; reason: {c['reason']}" if c.get("reason") else ""
            ext = " (extends the 5-question run)" if n == 10 else ""
            return (f"**{c['status']}** {c.get('have', 0)}/{n}{ext}; {c.get('seconds', 0)} s; "
                    f"generated {c.get('generated', 0)}, reused {c.get('reused', 0)}; {c.get('calls', 0)} calls{why}{tail}")
        cases_rerun = row.get("rerun", {})
        def label2(n):
            c = cases_rerun.get(str(n))
            if not c:
                return "-"
            ext = " (extends the 5 run)" if n == 10 else ""
            return (f"**{c['status']}** {c.get('have', 0)}/{n}{ext}; {c.get('seconds', 0)} s; generated {c.get('generated', 0)}, reused {c.get('reused', 0)}; "
                    f"{c.get('calls', 0)} calls" + (f"; reason: {c['reason']}" if c.get("reason") else "") +
                    ("; rejected " + ", ".join(f"{k} {v}" for k, v in c.get("rejected_by_stage", {}).items()) if c.get("rejected_by_stage") else ""))
        local = "/".join("OK" if row["local"][str(n)]["ok"] else "FAIL" for n in (5, 10))
        lines.append(f"| {row['title']} | {row['usable_passages']} | {row['usable_words']} | {local} | "
                     f"{row['eligible_cached']} | {label(5)} | {label(10)} | {label2(5)} | {label2(10)} |")
    lines.extend(["", "## Meaning and limitations", "",
                  "- Evidence OK means the real lecture passed the existing evidence-pool gate, candidate bundles were produced, and no unselected lecture entered them. It does not establish that 5/10 good questions can be generated.",
                  "- Live ready means an actual isolated quiz passed the current generation/solver/audit pipeline; it is not instructor or medical validation.",
                  "- Blocked means the shared AI connection was unavailable. It is not a failure of that lecture's content.",
                  "- Live 5 is a cold request per lecture. Live 10 uses accepted items from that lecture's 5-question request. These are distinct measurements.",
                  "- All original runtime stores are protected. New attempts and private keys live only in a temporary audit store."])
    if report.get("scratch"):
        lines.append(f"- Isolated audit store directory: `{report['scratch']}` (one database per lecture).")
    if report.get("protected_unchanged") is not None:
        lines.extend(["", "## Protected file comparison", ""])
        for name, same in report["protected_unchanged"].items():
            lines.append(f"- {name}: {'unchanged' if same else 'changed during audit; investigate concurrent app use; not restored/deleted' }.")
    notes = ROOT / "reports" / "quiz_all_lectures_notes_2026-10-20.md"
    if notes.exists():
        lines.extend(["", notes.read_text().rstrip()])
    REPORT.with_suffix(".md").write_text("\n".join(lines) + "\n")


def mark_blocked(before):
    report = json.loads(REPORT.with_suffix(".json").read_text())
    client = llm.make_client()
    probes = []
    for m in MODELS:
        start = time.perf_counter()
        try:
            client.with_options(timeout=15, max_retries=0).chat.completions.create(model=m, max_tokens=50, messages=[{"role": "user", "content": "Reply with the single word OK."}])
            probes.append({"model": m, "reachable": True, "seconds": round(time.perf_counter() - start, 1)})
        except Exception as exc:
            probes.append({"model": m, "reachable": False, "seconds": round(time.perf_counter() - start, 1), "error_type": type(exc).__name__,
                           "http_status": getattr(exc, "status_code", None), "detail": llm._plain_error(exc)[0]})
    report["gateway_after"] = probes
    if all(p["reachable"] for p in probes):
        print("gateway reachable: nothing to mark; re-run with --live --only <titles> instead")
        return
    for row in report["lectures"]:
        row.setdefault("live", {})
        for n in ("5", "10"):
            c = row["live"].get(n)
            if c is None or c.get("status") == "blocked" or (c.get("reason") == "gateway" and not c.get("calls")):
                row["live"][n] = {"status": "blocked", "reason": probes[0].get("detail") or "gateway"}
    report["blocked_reason"] = ("Live checks stopped part-way: the shared BullsAI gateway answered "
                                + "; ".join(f"{p['model']}: HTTP {p.get('http_status')} {p.get('detail')}" for p in probes if not p["reachable"])
                                + ". Cases marked Blocked were NOT run and are not content failures.")
    report["updated_utc"] = datetime.now(timezone.utc).isoformat()
    write_report(report)
    print("blocked cases marked:", [r["title"] for r in report["lectures"] if any(r["live"].get(n, {}).get("status") == "blocked" for n in ("5", "10"))])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--mark-blocked", action="store_true", help="probe the gateway once; if it fails, mark every lecture case that has no live result as blocked (no generation is attempted)")
    parser.add_argument("--only", nargs="*", help="re-run only these lecture titles (substring match); results go to 'rerun' beside the earlier 'live' results")
    args = parser.parse_args()
    before = protected()
    if args.mark_blocked:
        return mark_blocked(before)
    chunks = [json.loads(s) for s in (ROOT / "data/index/chunks.jsonl").read_text().splitlines() if s.strip()]
    titles = sorted({c["lecture"] for c in chunks if c["source_type"] == "notes"})
    searcher = SimpleNamespace(chunks=chunks, note_lectures=set(titles))
    ctx = qa.load_context()
    report = {"updated_utc": datetime.now(timezone.utc).isoformat(), "lectures": [], "gateway": [],
              "quiz_version": items.QUIZ_VERSION, "protected_before": before}
    bank = ReadOnlyBank()
    for title in titles:
        cs = [c for c in chunks if c["source_type"] == "notes" and c["lecture"] == title]
        passages = [p for c in cs if (p := evidence.passage_of(c, ctx))]
        row = {"title": title, "chunks": len(cs), "usable_passages": len(passages),
               "usable_words": sum(len(p["text"].split()) for p in passages), "local": {}, "live": {}}
        for n in (5, 10):
            req = {"mode": "materials", "n": n, "selected": [title]}
            pool = evidence.build_pool(req, searcher, [title], ctx, random.Random(7), web_lookup=None)
            candidates = pool.candidates(3 * n, random.Random(7)) if not pool.error else []
            scope_ok = all(p["lecture"] == title and p["tier"] in ("course", "verified")
                           for cand in candidates for p in cand["passages"])
            row["local"][str(n)] = {"ok": not pool.error and bool(candidates) and scope_ok,
                                      "error": pool.error, "candidate_count": len(candidates),
                                      "capacity_heuristic": sum(evidence.capacity(p) for p in pool.passages),
                                      "selected_scope_only": scope_ok}
        eligible = quiz.eligible_items(bank, searcher, [title], ctx,
                                      {"mode": "materials", "n": 10, "selected": [title]}, set(titles))
        row["eligible_cached"] = len(quiz.pick_unique(eligible, 10, random.Random(7)))
        report["lectures"].append(row)
    if args.only:
        old = json.loads(REPORT.with_suffix(".json").read_text())
        keep = {r["title"]: r for r in old["lectures"]}
        for row in report["lectures"]:
            if row["title"] in keep:
                row["live"] = keep[row["title"]].get("live", {})
                row["rerun"] = keep[row["title"]].get("rerun", {})
        report["gateway_baseline"] = old.get("gateway")
        report["scratch_baseline"] = old.get("scratch")
    print(json.dumps({"local_lectures": len(titles), "evidence_5_ok": sum(r['local']['5']['ok'] for r in report['lectures']),
                      "evidence_10_ok": sum(r['local']['10']['ok'] for r in report['lectures'])}), flush=True)
    write_report(report)
    if args.live:
        client = llm.make_client()
        with ThreadPoolExecutor(max_workers=2) as ex:
            report["gateway"] = list(ex.map(lambda model: probe(client, model), MODELS))
        print(json.dumps({"gateway": report["gateway"]}), flush=True)
        unavailable = not all(p["reachable"] for p in report["gateway"])
        scratch = Path(tempfile.mkdtemp(prefix="anatovision_all_lectures_"))
        report["scratch"] = str(scratch)
        rt = SimpleNamespace(searcher=searcher, client=client, model=MODELS[0], rewrite_model=MODELS[0])
        rows = sorted(report["lectures"], key=lambda r: ("Lecture 06 - " not in r["title"], r["title"]))
        if args.only:
            rows = [r for r in rows if any(o.lower() in r["title"].lower() for o in args.only)]
        slot = "rerun" if args.only else "live"
        for row in rows:
            store = QuizStore(scratch / (hashlib.sha256(row["title"].encode()).hexdigest()[:12] + ".db"))
            for n in (5, 10):
                if unavailable:
                    row.setdefault(slot, {})[str(n)] = {"status": "blocked", "reason": "shared_gateway_unreachable"}
                    continue
                req = {"mode": "materials", "n": n, "selected": [row["title"]]}
                start = time.perf_counter()
                out = quiz.new_quiz("isolated-audit", [row["title"]], req, rt,
                                    store=store, ctx=ctx, rng=random.Random(7), web_lookup=None)
                detail = store.runs(1)[0]
                row.setdefault(slot, {})[str(n)] = {"status": out["status"], "reason": out.get("reason"), "have": out["have"],
                                        "seconds": round(time.perf_counter() - start, 1),
                                        **{k: detail.get(k, 0) for k in ("calls", "drafts", "reused", "generated", "gateway_errors")},
                                        "rejected_by_stage": detail.get("rejected_by_stage", {}),
                                        "rejections": detail.get("rejected", [])}
                print(json.dumps({"lecture": row["title"], "n": n, "slot": slot, **row[slot][str(n)]}), flush=True)
                if out.get("reason") == "gateway":
                    unavailable = True
                report["updated_utc"] = datetime.now(timezone.utc).isoformat()
                write_report(report)
        if unavailable:
            report["blocked_reason"] = ("Live checks cannot be completed while the shared BullsAI gateway is unreachable. "
                                        "The remaining cases are explicitly marked blocked, not passed or content failures. "
                                        "Re-run this script with --live after connectivity is restored.")
    report["protected_unchanged"] = {k: fingerprint(ROOT / "data" / k) == v for k, v in before.items()}
    report["updated_utc"] = datetime.now(timezone.utc).isoformat()
    write_report(report)
    print("Reports:", str(REPORT.with_suffix('.md')), str(REPORT.with_suffix('.json')), flush=True)


if __name__ == "__main__":
    main()
