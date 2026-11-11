"""Live checks of the STAGED revised data (data/staging_v2) with the real BullsAI model: questions and one guide station check.  Nothing is logged or saved."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.update(LLM_PROVIDER="bullsai", WEB_FALLBACK="off", RERANK=os.environ.get("RERANK", "on"))
from src.ingest import stage as ST  # noqa: E402

QUESTIONS = ["What are the boundaries and contents of the femoral triangle?", "apex", "What is the nerve supply of the hypothenar muscles?",
             "How is the neck divided into triangles?",                                 # a lecture the revision rewrote (now Lecture 22)
             "What are the boundaries of the anterior triangle of the neck?", "What does the deep cervical fascia do?",
             "What are the dural venous sinuses?",                                      # only in the earlier version of Lecture 17
             "How do I expose the femoral triangle?"]


def main():
    stage = ROOT / "data" / "staging_v2"
    with ST.use(stage):
        from src import auth, llm, service
        from src import student_view as sv
        from src.modes import guide_slides as GS
        from app_api import catalog
        rt = service.build_runtime(warm=True)
        for q in (sys.argv[1:] or QUESTIONS):
            res = service.ask_for_student(q, "", True, None, runtime=rt, log=False)["view"]
            print(f"\nQ: {q}\n   status={res['status']} footer={res['footer']!r}")
            print("   " + res["answer_text"][:700].replace("\n", "\n   "))
            print("   sources:", [(s["lecture"][:40], s.get("superseded", "")) for s in res["sources"]][:4])
            assert sv.leaks({k: res[k] for k in ("answer_text", "blocks", "footer", "notice")}) == [], "leak"
        g = next(x for x in catalog.guides() if x["class_number"] == 17)
        sess = GS.SlideGuideSession.open(rt.client, rt.model, g["entry"])
        sess.goto(2)
        turn = sess.assess("I located the medial side of the knee and transected the sartorius, gracilis and semitendinosus tendons at the pes anserinus.")
        print("\nGUIDE", g["title"], "station 2:", turn["detail"]["verdict"], "|", turn["detail"]["feedback"])


main()
