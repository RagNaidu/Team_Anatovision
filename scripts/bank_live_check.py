"""Live check: a 5-question quiz from Lecture 08 with the REAL BullsAI, on THROW-AWAY quiz and bank databases (the live ones are never opened for writing).
It seeds the temp bank with an approved practice question, a draft, an exam-secure and a retired one (all fake) and shows what the quiz used."""
import hashlib, random, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
from src import service as svc
from src.modes import qa
from src.qbank import store as BS
from src.quiz import service as qs
from src.quiz.store import QuizStore

LEC = "Lecture 08 - Anterior and Medial Thigh"
LIVE = ["data/users.json", "data/quizzes.db", "data/processed/sections.jsonl", "data/index/chunks.jsonl", "reports/factcheck_all.json"]
md5 = lambda: {p: hashlib.md5((ROOT / p).read_bytes()).hexdigest() if (ROOT / p).exists() else None for p in LIVE}
before = md5()
tmp = Path(tempfile.mkdtemp(prefix="bank_live_"))
BS.DB_PATH = tmp / "bank.db"
bank = BS.BankStore()
opts = lambda *t: [{"id": "ABCD"[i], "text": x} for i, x in enumerate(t)]
base = {"lecture": LEC, "region": "Lower limb", "source": "instructor"}
bank.create({**base, "lead_in": "Which muscle forms the lateral border of the femoral triangle?", "options": opts("Sartorius", "Gracilis", "Pectineus", "Adductor magnus"), "answer": "A", "explanation": "Sample (fake) explanation.", "status": "approved", "use": "practice", "tags": ["sample"], "sample": True}, "sample")
bank.create({**base, "lead_in": "SECRETEXAM Which nerve supplies the pectineus muscle of the thigh?", "options": opts("Femoral nerve", "Obturator nerve", "Tibial nerve", "Sciatic nerve"), "answer": "A", "status": "approved", "use": "exam_secure", "sample": True}, "sample")
bank.create({**base, "lead_in": "DRAFTONLY Which vein drains the lateral thigh?", "options": opts("Femoral vein", "Popliteal vein", "Small saphenous vein", "Gluteal vein"), "answer": "A", "status": "draft", "use": "practice", "sample": True}, "sample")
bank.create({**base, "lead_in": "RETIRED Which artery supplies the adductor muscles?", "options": opts("Obturator artery", "Femoral artery", "Popliteal artery", "Gluteal artery"), "answer": "A", "status": "retired", "use": "practice", "sample": True}, "sample")
store = QuizStore(tmp / "quizzes.db")
t0 = time.time()
rt = svc.build_runtime()
print(f"runtime {time.time() - t0:.1f}s")
t0 = time.time()
out = qs.new_quiz("live-check", [LEC], {"mode": "materials", "n": 5, "selected": [LEC]}, rt, store=store, ctx=qa.load_context(), rng=random.Random(5), web_lookup=None)
print(f"quiz {time.time() - t0:.1f}s ->", {k: out[k] for k in ("status", "reason", "have", "reused", "generated", "message")})
if out["quiz_id"]:
    q = store.get_quiz("live-check", out["quiz_id"])
    for k, iid in enumerate(q["item_ids"], 1):
        it = store.item(iid)
        print(f"  {k}. [{'bank' if it.get('bank_id') else 'AI'}] {it['lead_in']}  -> {[o['text'] for o in it['options'] if o['id'] in it['answer_ids']][0]}")
    served = " ".join(store.item(i)["lead_in"] for i in q["item_ids"])
    print("exam-secure / draft / retired leaked into the quiz:", any(w in served for w in ("SECRETEXAM", "DRAFTONLY", "RETIRED")))
rows = bank.all()
print("bank after:", {(r["data"]["source"], r["data"]["status"], r["data"]["use"]) for r in rows if not r["data"]["sample"]}, "| new AI rows:", sum(r["data"]["source"] == "ai" for r in rows))
for r in rows:
    if r["data"]["source"] == "ai":
        print("  AI draft:", r["data"]["lead_in"], "| flags:", [f["code"] for f in r["flags"]])
print("live data unchanged:", md5() == before)
