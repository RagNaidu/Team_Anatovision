"""Live check of the dissection-guide walk-through: real model (gemma), no logging (the session never writes the question log), then
gpt-oss-120b checks that every claim in each piece of feedback is supported by the station's slide text.  Writes reports/guide_slides_check.md."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src import llm
from src.ingest import guides as G
from src.modes import guide_slides as GS

CASES = {
 17: {12: ("I found the iliofemoral ligament and checked its distal end attaches to the intertrochanteric line of the femur, with the proximal end on the anterior inferior iliac spine.",
           "The iliofemoral ligament attaches to the pubic ramus and the ischial spine.", "I can see a ligament."),
      6: ("I opened and removed the posterior wall of the joint capsule, found the posterior cruciate ligament, and saw the cruciate ligaments lie outside the synovial cavity but inside the capsule.",
          "I cut the anterior wall and saw the cruciate ligaments floating inside the synovial cavity.", "I opened it up."),
      10: ("The medial meniscus is firmly attached to the tibial collateral ligament, while the lateral meniscus is not attached to the fibular collateral ligament.",
           "The lateral meniscus is firmly attached to the fibular collateral ligament and the medial meniscus is free.", "I looked at the menisci.")},
 14: {5: ("I pushed my fingers between gluteus maximus and medius, cut the maximus close to the ilium, sacrum and coccyx, detached it from the sacrotuberous ligament and reflected it laterally.",
          "I cut the gluteus medius off the greater trochanter and reflected it upward.", "I removed the big muscle."),
      6: ("I identified the piriformis passing through the greater sciatic foramen and the sciatic nerve below it.",
          "The sciatic nerve runs above the piriformis and the superior gluteal vessels run below it.", "I see some muscle and nerves."),
      8: ("I identified the superior gluteal vessels and nerves above the piriformis, covered by gluteus medius, and separated the medius from the gluteus minimus.",
          "I found the pudendal nerve running above the piriformis next to the superior gluteal artery below it.", "I cleaned the area.")}}

SYS = ("You are a strict fact-checker. You get the SLIDE TEXT of a dissection-guide station, the STUDENT's description and the FEEDBACK a tutor gave. "
       "Is every claim in the FEEDBACK supported by the slide text (or just a restatement of what the student wrote)? "
       'Reply with ONE JSON object: {"verdict": "yes"|"partly"|"no", "reason": "one line", "unsupported": ["quoted claims"]}.')
SCHEMA = {"type": "object", "properties": {"verdict": {"type": "string", "enum": ["yes", "partly", "no"]}, "reason": {"type": "string"},
          "unsupported": {"type": "array", "items": {"type": "string"}}}, "required": ["verdict", "reason", "unsupported"], "additionalProperties": False}
LABEL = ("correct", "wrong", "vague")

def main():
    client = llm.make_client(); model = llm.default_model()
    rows = []
    for num, stations in CASES.items():
        e = next(e for e in G.map_by_file().values() if e["class_number"] == num)
        slides = GS.slides_of(e["file"])
        sess = GS.SlideGuideSession.open(client, model, e, slides)
        by_slide = {s["n"]: s for s in slides}
        for n, descs in stations.items():
            sess.goto(n)
            shown = sess.state()["station"]
            slide_text = " ".join(" ".join(by_slide[k]["texts"]) for k in shown["slides"])
            shown_ok = all(t[:40] in slide_text.replace("\n", " ") or t[:25] in slide_text for t in shown["steps"][:3]) and shown["cite"].startswith(f"Dissection Guide, {e['class_label']}, slide")
            for lab, d in zip(LABEL, descs):
                sess.goto(n)
                t0 = time.perf_counter(); turn = sess.assess(d); sec = round(time.perf_counter() - t0, 1)
                det = turn["detail"]
                row = {"guide": e["display_name"], "station": n, "slides": shown["slides"], "kind": lab, "description": d, "seconds": sec, "verdict": det["verdict"],
                       "feedback": det["feedback"], "station_ok": shown_ok, "cite": shown["cite"], "station_text": shown["text"]}
                for _ in (1, 2):
                    try:
                        j, _u = llm.complete_json(client, SYS, [{"role": "user", "content": f"SLIDE TEXT:\n{shown['text']}\n\nSTUDENT:\n{d}\n\nFEEDBACK:\n{det['feedback']}"}], 3000, SCHEMA, "openai/gpt-oss-120b")
                        row["judge"] = j; break
                    except Exception as ex:
                        row["judge"] = {"verdict": "error", "reason": str(ex)[:100], "unsupported": []}
                rows.append(row)
                print(f"{num} s{n} {lab:8} {sec:4}s {det['verdict']:7} judge={row['judge']['verdict']:6} | {det['feedback'][:110]}", flush=True)
    Path(ROOT / "reports" / "guide_slides_check.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
main()
