"""Live check of the JSON API as a student, over real HTTP, against the sandbox server (scripts/api_sandbox.py). No logging to real data.

    SANDBOX_DIR=/tmp/anatovision-sandbox .venv/bin/python scripts/api_sandbox.py --port 8000      # terminal 1 (needs the UB network/VPN for BullsAI)
    SANDBOX_DIR=/tmp/anatovision-sandbox .venv/bin/python scripts/api_live_check.py               # terminal 2

Steps: ask (femoral triangle, "apex", a procedural question, a Wikipedia question, amoxicillin), walk one guide station, build a 5-question quiz
from one lecture, answer it, submit, read the results. Every response is validated against the contract's response models, checked for
student-safe leaks and for [n] markers without a source. A step that needs the model while BullsAI cannot be reached is reported BLOCKED
(never retried more than once, never sent to another provider).
--seed-quiz additionally runs the quiz flow (answer, submit, results) on SEEDED questions written into the sandbox quiz database, so the
quiz JSON can be checked while the model is unreachable. Seeded questions are test data, not generated ones, and the report says so.
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pydantic import TypeAdapter  # noqa: E402

from app_api import schemas as S  # noqa: E402
from src import student_view as sv  # noqa: E402

LINES = []


def say(text=""):
    print(text, flush=True)
    LINES.append(text)


def leaks_in_values(obj):
    found = []

    def walk(x):
        if isinstance(x, str):
            found.extend(sv.leaks(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(obj)
    return found


def conforms(model, data):
    try:
        TypeAdapter(model).validate_python(data)
        return True
    except Exception as exc:
        return f"DOES NOT MATCH: {str(exc)[:200]}"


class Check:
    def __init__(self, base, box):
        self.c = httpx.Client(base_url=base, timeout=300)
        pw = (Path(box) / "PASSWORD.txt").read_text().strip()
        r = self.c.post("/api/auth/login", json={"username": "student", "password": pw})
        assert r.status_code == 200, r.text
        self.blocked = 0

    def ask(self, name, question):
        chat = self.c.post("/api/chats").json()
        t0 = time.time()
        r = self.c.post("/api/ask", json={"chat_id": chat["id"], "question": question, "length": "brief"})
        dt = time.time() - t0
        if r.status_code != 200:
            say(f"- **{name}** `{question}`: HTTP {r.status_code} {r.text[:200]}")
            return None
        m = r.json()
        markers = sorted({int(n) for n in re.findall(r"\[(\d+)\]", m["markdown"])})
        ns = [s["n"] for s in m["sources"]]
        blocked = m["kind"] == "error"
        self.blocked += blocked
        say(f"- **{name}** `{question}` ({dt:.0f} s): kind `{m['kind']}`{' BLOCKED (the model could not be reached)' if blocked else ''}; contract: {conforms(S.Message, m)}; "
            f"markers {markers} vs sources {ns}: {'ok' if set(markers) <= set(ns) else 'MARKER WITHOUT SOURCE'}; leaks: {sv.leaks(m) or 'none'}")
        for s in m["sources"]:
            say(f"    - [{s['n']}] {s['type']}: {s['title']} / {s['subtitle']} (lecture_id {s['lecture_id']}, url {s['url']}, licence {s['license']}, retrieved {s['retrieved_at']})")
        if m["footer"]:
            say(f"    - footer: {m['footer']}")
        say("    - " + m["markdown"][:500].replace("\n", " "))
        again = self.c.get(f"/api/chats/{chat['id']}").json()
        same = again["messages"][-1]["markdown"] == m["markdown"] and again["messages"][-1]["id"] == m["id"]
        say(f"    - reopening the chat returns the same message: {same}")
        return m

    def guide(self, model=True):
        guides = self.c.get("/api/guides").json()
        say(f"- guides: {len(guides)}; contract: {conforms(list[S.GuideItem], guides)}")
        gid = "class-10"
        stations = self.c.get(f"/api/guides/{gid}/stations").json()
        say(f"- stations of {gid}: {len(stations)}; contract: {conforms(list[S.Station], stations)}; leaks: {sv.leaks(stations) or 'none'}")
        st = next(s for s in stations if not s["image_only"])
        if not model:
            say("- check a description: BLOCKED (BullsAI unreachable; --skip-model, not retried)")
            self.blocked += 1
        for label, text in () if not model else (("student repeats the first steps", " ".join(st["steps"][:3])), ("unrelated description", "I can see the stomach and the small intestine.")):
            r = self.c.post(f"/api/guides/{gid}/stations/{st['index']}/check", json={"description": text})
            if r.status_code == 200:
                b = r.json()
                say(f"- check ({label}): `{b['verdict']}`; contract: {conforms(S.CheckOut, b)}; feedback: {b['feedback_markdown']}; source: {b['sources'][0]['title']}, {b['sources'][0]['subtitle']}; leaks: {leaks_in_values(b) or 'none'}")
            else:
                self.blocked += r.status_code == 502
                say(f"- check ({label}): HTTP {r.status_code} {r.json().get('error')}{' BLOCKED (the model could not be reached)' if r.status_code == 502 else ''}")
        lec = self.c.get("/api/lectures/L09-the-hand/stations").json()
        say(f"- lecture-notes sample stations: {len(lec)}; contract: {conforms(list[S.Station], lec)}; leaks: {sv.leaks(lec) or 'none'}")

    def quiz_from_model(self, lecture_id="L09-the-hand"):
        r = self.c.post("/api/quiz/build", json={"mode": "materials", "lecture_ids": [lecture_id], "n": 5, "reviewed_only": False})
        assert r.status_code == 200, r.text
        jid, last = r.json()["job_id"], None
        end = time.time() + 900
        while time.time() < end:
            j = self.c.get(f"/api/quiz/jobs/{jid}").json()
            if (j["have"], j["note"]) != last:
                last = (j["have"], j["note"])
                say(f"    - progress: {j['have']} of {j['requested']}: {j['note']}")
            if j["done"]:
                break
            time.sleep(3)
        say(f"- build job: contract {conforms(S.JobStatus, j)}; result {json.dumps(j['result'])}")
        if j["result"]["status"] == "ready":
            self.take(j["result"]["quiz_id"], "generated by the model")
        else:
            gateway = j["result"]["reason"] in ("gateway", "quota")
            self.blocked += gateway
            say(f"  - no quiz was started ({j['result']['reason']}){': BLOCKED (the model could not be reached)' if gateway else ''}")

    def take(self, qid, how):
        say(f"- quiz {qid} ({how})")
        q = self.c.get(f"/api/quiz/{qid}").json()
        text = json.dumps(q)
        hidden = not any(f'"{k}"' in text for k in ("answer_ids", "explanation", "alternatives", "evidence", "correct", "spans"))
        say(f"  - open quiz: contract {conforms(S.OpenQuiz, q)}; key/explanations/evidence absent before submit: {hidden}; leaks: {sv.leaks(q) or 'none'}")
        early = self.c.get(f"/api/quiz/{qid}/results")
        say(f"  - results before submit: HTTP {early.status_code} {early.json()}")
        for i, qq in enumerate(q["questions"]):
            r = self.c.put(f"/api/quiz/{qid}/answers/{i}", json={"option_ids": [qq["options"][i % 5]["id"]]})
            assert r.status_code == 200, r.text
        self.c.put(f"/api/quiz/{qid}/current", json={"index": 2})
        res = self.c.post(f"/api/quiz/{qid}/submit")
        assert res.status_code == 200, res.text
        body = res.json()
        again = self.c.get(f"/api/quiz/{qid}/results").json()
        say(f"  - submit: score {body['score']} of {body['length']}; contract {conforms(S.Results, body)}; results endpoint identical: {again == body}; "
            f"leaks (values): {leaks_in_values(body) or 'none'}")
        say(f"  - history: {self.c.get('/api/quiz/history').json()}")


def seed(box):
    """Five test questions in the SANDBOX quiz database (never the real one)."""
    os.environ["ANATOVISION_QUIZ_PATH"] = str(Path(box) / "quizzes.db")
    from src.quiz import items as qi
    from src.quiz import store as qstore
    qstore.DB_PATH = Path(box) / "quizzes.db"
    st = qstore.QuizStore()
    its = []
    for i in range(5):
        pid = f"seed{i}"
        text = f"SEEDED TEST PASSAGE {i}: the median nerve passes through the carpal tunnel."
        sup = [{"source_id": pid, "span": "the median nerve passes through the carpal tunnel"}]
        its.append({"item_id": f"seed-{int(time.time())}-{i}", "selection_mode": "single", "stem": "", "lead_in": f"SEEDED TEST QUESTION {i}: which nerve passes through the carpal tunnel?",
                    "options": [{"id": c, "text": f"Seeded option {c}"} for c in "ABCDE"], "answer_ids": ["B"], "explanation": "Seeded test explanation.",
                    "key_support": sup, "explanation_support": sup, "objective": "carpal tunnel",
                    "alternatives": {c: {"why_wrong": f"Seeded reason {c} is wrong.", "support": sup} for c in "ACDE"},
                    "evidence": {pid: {"id": pid, "label": "Lecture 09 - The Hand > Nerves", "tier": "course", "kind": "notes", "lecture": "Lecture 09 - The Hand",
                                       "guide": "", "url": "", "text": text, "license": ""}},
                    "tiers": ["course"], "scope": {}, "checks": {}, "review": {"status": "unreviewed"}, "created": time.time(), "version": qi.QUIZ_VERSION})
    st.save_items(its)
    return st.create_quiz("student", [i["item_id"] for i in its], 5, {"mode": "materials", "selected": ["Lecture 09 - The Hand"], "n": 5}, "open")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--sandbox-dir", default=os.environ.get("SANDBOX_DIR", "/tmp/anatovision-sandbox"))
    ap.add_argument("--seed-quiz", action="store_true")
    ap.add_argument("--skip-model", action="store_true", help="do not call the model (BullsAI is known to be unreachable): report those steps as BLOCKED")
    ap.add_argument("--report", default="")
    a = ap.parse_args()
    chk = Check(a.base, a.sandbox_dir)
    say(f"# API live check ({time.strftime('%Y-%m-%d %H:%M')}), as `student`, sandbox data only\n")
    say("## Ask")
    for name, q in (("femoral triangle", "What are the boundaries and contents of the femoral triangle?"), ("apex", "apex"),
                    ("procedural", "How do I dissect the gluteal region?"), ("wikipedia", "What is Broca's area?"),
                    ("amoxicillin", "What dose of amoxicillin should I take for a sore throat?")):
        if a.skip_model:
            say(f"- **{name}** `{q}`: BLOCKED (BullsAI unreachable; --skip-model, not retried)")
            chk.blocked += 1
        else:
            chk.ask(name, q)
    say("\n## Guide")
    chk.guide(model=not a.skip_model)
    say("\n## Quiz")
    if a.skip_model:
        say("- build a 5-question quiz from one lecture: BLOCKED (BullsAI unreachable; --skip-model, not retried)")
        chk.blocked += 1
    else:
        chk.quiz_from_model()
    if a.seed_quiz:
        say("\n## Quiz flow on SEEDED test questions (not generated by the model)")
        chk.take(seed(a.sandbox_dir), "seeded test questions")
    say(f"\nBlocked steps (model unreachable): {chk.blocked}")
    if a.report:
        Path(a.report).write_text("\n".join(LINES) + "\n", encoding="utf-8")
