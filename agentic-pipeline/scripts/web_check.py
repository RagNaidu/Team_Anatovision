"""One live run per question through the real pipeline (web fallback on, Wikipedia on), no logging, then a judge model checks each web
answer against the fetched text. Writes reports/web_wikipedia_check.md.   .venv/bin/python scripts/web_check.py "Q1" "Q2" ..."""
import json, os, sys, time
from datetime import date
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["WEB_FALLBACK"] = "on"
from scripts.live_ask import sandbox  # noqa: E402

JUDGE = os.environ.get("JUDGE_MODEL", "openai/gpt-oss-120b")
SYS = ("You are a strict fact-checker. You get a QUESTION, an ANSWER and the FETCHED WIKIPEDIA TEXT the answer was written from. Is every claim of the "
       "ANSWER supported by that text (paraphrase is fine)? Ignore the closing line 'Ask for more detail...'. Reply with ONE JSON object: "
       '{"verdict": "yes"|"partly"|"no", "reason": "one line", "unsupported": ["quoted claims"]}.')
SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["yes", "partly", "no"]}, "reason": {"type": "string"},
          "unsupported": {"type": "array", "items": {"type": "string"}}}, "required": ["verdict", "reason", "unsupported"], "additionalProperties": False}

def main():
    sandbox()
    from src import llm, service, student_view as sv
    rt = service.build_runtime()
    jc = llm.make_client()
    rows = []
    for q in sys.argv[1:]:
        t = time.perf_counter()
        res = service.ask(q, "", True, None, runtime=rt, log=False)
        sec = round(time.perf_counter() - t, 1)
        view = sv.build(res)
        row = {"q": q, "sec": sec, "status": res["status"], "mode": res["mode"], "reason": res["reason"], "answer": res["answer_text"],
               "label": view.get("web_label", ""), "pages": [(c["title"], c["source_url"], c["retrieved"], c["license"]) for c in res["retrieved_chunks"] if c["source_type"] == "web"],
               "searched": any(e["kind"] == "web_lookup" for e in res["events"]), "leaks": sv.leaks(view)}
        if res["web"]:
            fetched = "\n\n".join(f"[{c['title']}]\n{c['text']}" for c in res["retrieved_chunks"])
            for _ in (1, 2):
                try:
                    row["judge"], _u = llm.complete_json(jc, SYS, [{"role": "user", "content": f"QUESTION: {q}\n\nANSWER:\n{res['answer_text']}\n\nFETCHED TEXT:\n{fetched}"}], 3000, SCHEMA, JUDGE)
                    break
                except Exception as e:
                    row["judge"] = {"verdict": "error", "reason": str(e)[:120], "unsupported": []}
        rows.append(row)
        print(f"{sec:5}s {res['status']:10} {res['mode']:6} pages={[p[0] for p in row['pages']]} searched={row['searched']} judge={row.get('judge', {}).get('verdict')} | {q}", flush=True)
    Path(ROOT / "reports" / "web_wikipedia_check.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))

main()
