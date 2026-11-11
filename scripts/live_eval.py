"""Live evaluation: the real pipeline (BullsAI answer model, reranker ON, web fallback ON, real index) on ~30 questions, then an independent
judge model (default openai/gpt-oss-120b) checks every answer against the passages it cites.

No-logging method (same as scripts/live_ask.py): service.ask(log=False) and flags / question log / settings pointed at a temp folder.

  .venv/bin/python scripts/live_eval.py            -> reports/live_eval_<date>.md and .json
"""
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["WEB_FALLBACK"] = "on"
os.environ["RERANK"] = "on"

from scripts.live_ask import sandbox  # noqa: E402

JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "openai/gpt-oss-120b")
HAND = "Lecture 09 - The Hand"

# (group, question, follow-up-of index or None, allowed lectures or None)
QUESTIONS = [
    ("keyword", "apex", None, None), ("keyword", "thenar", None, None), ("keyword", "hypothenar", None, None),
    ("keyword", "trochanter", None, None), ("keyword", "nerve supply", None, None), ("keyword", "what is a foramen?", None, None),
    ("normal", "What are the walls of the middle ear?", None, None),
    ("normal", "What are the boundaries and contents of the femoral triangle?", None, None),
    ("normal", "What does the sartorius do?", None, None), ("normal", "Which muscles make up the rotator cuff?", None, None),
    ("normal", "What nerve supplies the muscles of the hypothenar eminence?", None, None),
    ("normal", "What are the contents of the carpal tunnel?", None, None),
    ("procedural", "How do I reflect the skin over the thigh?", None, None),
    ("procedural", "What are the steps to expose the femoral triangle?", None, None),
    ("procedural", "How do I remove the gluteus maximus?", None, None),
    ("procedural", "How do I identify the piriformis and the sciatic nerve?", None, None),
    ("procedural", "How do I open the adductor canal?", None, None),
    ("procedural", "How do I open the carpal tunnel?", None, None),
    ("procedural", "How do I remove the brain?", None, None),
    ("procedural", "How do I open the pericardium?", None, None),
    ("web", "What is Broca's area?", None, None), ("web", "What is the thyroglossal duct?", None, None),
    ("web", "What is the glomus tympanicum?", None, None),
    ("refusal", "amoxicillin", None, None), ("refusal", "Who won the 2022 World Cup?", None, None),
    ("follow-up", "What is the roof made of?", 6, None), ("follow-up", "And which nerve is the most lateral?", 7, None),
    ("follow-up", "Where does it insert?", 8, None), ("follow-up", "What do I identify after that?", 14, None),
    ("outside-access", "What are the walls of the middle ear?", None, [HAND]),
    ("outside-access", "How do I remove the gluteus maximus?", None, [HAND]),
]

JUDGE_SYSTEM = ("You are a strict fact-checker. You get a QUESTION, an ANSWER, and the CITED PASSAGES the answer relies on. Decide whether "
                "every claim in the ANSWER is supported by the CITED PASSAGES (paraphrase is fine; a claim that the passages do not state, "
                "or that adds detail beyond them, is unsupported). Ignore the closing line 'Ask for more detail...' and notices such as 'Dr. Inglis is reviewing this line'. "
                "Reply with ONE JSON object: {\"verdict\": \"yes\" | \"partly\" | \"no\", \"reason\": \"one line\", \"unsupported\": [\"each unsupported claim, quoted\"]}. "
                "yes = all claims supported; partly = some claims unsupported; no = most claims unsupported or contradicted.")
JUDGE_SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["yes", "partly", "no"]}, "reason": {"type": "string"},
                                                 "unsupported": {"type": "array", "items": {"type": "string"}}},
                "required": ["verdict", "reason", "unsupported"], "additionalProperties": False}


def judge(client, question, res):
    from src import llm
    cited = []
    for c in res["citations"]:
        if c["matched"] and c["chunk"] is not None and c["chunk"] not in [x[0] for x in cited]:
            ch = res["retrieved_chunks"][c["chunk"]]
            cited.append((c["chunk"], f"[{c['cite']}]\n{ch['text']}"))
    user = (f"QUESTION: {question}\n\nANSWER:\n{res['answer_text']}\n\nCITED PASSAGES:\n" + "\n\n".join(t for _, t in cited))
    last = ""
    for attempt in (1, 2):
        try:
            data, _ = llm.complete_json(client, JUDGE_SYSTEM, [{"role": "user", "content": user}], 3000, JUDGE_SCHEMA, JUDGE_MODEL)
            return data
        except Exception as exc:                      # one retry only
            last = f"{type(exc).__name__}: {exc}"
    return {"verdict": "error", "reason": last[:200], "unsupported": []}


def event_time(res, kind):
    return next((e["t"] for e in res["events"] if e["kind"] == kind), None)


def main():
    sandbox()
    from src import llm, service
    from src import query as qry
    from src import student_view as sv
    rt = service.build_runtime()
    jclient = llm.make_client()
    rows = []
    for i, (group, q, fu, allowed) in enumerate(QUESTIONS):
        history = None
        if fu is not None:
            history = [{"question": QUESTIONS[fu][1], "answer": qry.short_answer(rows[fu]["res"]["answer_text"])}]
        t0 = time.perf_counter()
        res = service.ask(q, "", True, allowed, runtime=rt, log=False, history=history)
        sec = round(time.perf_counter() - t0, 1)
        view = sv.build(res)
        answered = res["status"] in ("answered", "access_limited") and bool(res["citations"])
        row = {"i": i, "group": group, "question": q, "followup_of": QUESTIONS[fu][1] if fu is not None else "", "allowed": allowed,
               "seconds": sec, "status": res["status"], "reason": res["reason"], "mode": res["mode"], "tier": res["tier"],
               "search_query": res["search_query"], "n_citations": len(res["citations"]), "n_unmatched": res["n_unmatched"],
               "leaks": sv.leaks(view), "answer": res["answer_text"], "footer": view["footer"], "sources_list": [e["label"] + (" -> " + e["url"] if e["url"] else "") for e in view["sources_list"]], "web": res["web"], "web_urls": res["web_urls"],
               "cites": [c["cite"] for c in res["citations"]], "res": res}
        if answered:
            row["judge"] = judge(jclient, q, res)
        # the time the web tier added: everything after the ordinary search had finished and found nothing
        if res["web"] or any(e["kind"] == "web_lookup" for e in res["events"]):
            row["web_extra_seconds"] = round(sec - (event_time(res, "threshold") or 0), 1)
        cov = [e for e in res["events"] if e["kind"] == "coverage_check"]
        if cov:                                              # what the OpenStax-only coverage check (and the Wikipedia fetch after it) added
            wl = [e for e in res["events"] if e["kind"] == "web_lookup"]
            row["coverage_seconds"] = cov[0]["detail"]["seconds"]
            row["coverage_web_seconds"] = wl[0]["detail"]["seconds"] if wl else 0.0
            row["coverage_missing"] = cov[0]["detail"]["missing"]
        rows.append(row)
        print(f"[{i + 1}/{len(QUESTIONS)}] {group:14} {sec:5.1f}s {res['status']:14} {res['mode']:6} {res['tier']:8} "
              f"judge={row.get('judge', {}).get('verdict', '-'):6} {q}", flush=True)
    slim = [{k: v for k, v in r.items() if k != "res"} for r in rows]
    out = ROOT / "reports" / f"live_eval_{date.today().isoformat()}"
    out.with_suffix(".json").write_text(json.dumps(slim, indent=2, ensure_ascii=False), encoding="utf-8")
    print("saved", out.with_suffix(".json"))


if __name__ == "__main__":
    main()
