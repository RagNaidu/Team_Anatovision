"""OCR the cropped guide pictures and save DRAFT label pins (plus arrows where a leader line is detected). Never approves anything. Also counts OCR lines that look like step text
inside a picture (there should be none). Usage: python scripts/guide_ocr_drafts.py [--only class-17]. Writes reports/guide_ocr_drafts.json."""
import argparse
import json
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from PIL import Image
from app_api import catalog
from src import guide_images as GI
from src import guide_ocr_marks as OM
from src import ocr
from src.guide_marks import MarkStore
from src.modes import guide_slides as GS

ap = argparse.ArgumentParser()
ap.add_argument("--only")
a = ap.parse_args()
if not ocr.backend():
    sys.exit("No OCR backend (needs ocrmac on macOS, or pytesseract with tesseract). Nothing was done.")
store = MarkStore()
sections = [json.loads(l) for l in (ROOT / "data" / "processed" / "sections.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
report = {}
for g in catalog.guides():
    if a.only and g["id"] != a.only:
        continue
    t0 = time.time()
    stations = GS.build_stations(GS.slides_of(g["file"]), g["entry"]["class_label"])
    notes = " ".join(s["text_clean"] for s in sections if s["lecture_id"] in g["lecture_ids"])
    guide_text = " ".join(" ".join(st["steps"]) + " " + st["title"] for st in stations)
    vocab = OM.vocabulary(guide_text, notes)
    station_of = {n: st for st in stations for n in st["slides"]}
    r = {"pictures": 0, "pins": 0, "arrows": 0, "linked": 0, "step_text_lines": 0}
    for n, e in GI.meta(g["id"])["slides"].items():
        n = int(n)
        for c in e["crops"]:
            if not GI.has_image(g["id"], n, c["k"]) or n not in station_of:
                continue
            img = Image.open(GI.crop_path(g["id"], n, c["k"])).convert("RGB")
            img.thumbnail((2000, 2000))
            existing = [(m["geom"].get("x", 0), m["geom"].get("y", 0), m["text"]) for m in store.list(g["id"], [n]) if m["kind"] == "label" and m["crop"] == c["k"] and m["source"] != "ocr"]      # the OCR drafts of this picture are being redone: only other labels count
            marks, info = OM.draft_picture(img, station_of[n]["steps"], vocab, existing)
            store.replace_auto_drafts(g["id"], n, marks, by="ocr", crop=c["k"], source="ocr")
            r["pictures"] += 1
            r["pins"] += sum(m["kind"] == "label" for m in marks)
            r["arrows"] += sum(m["kind"] == "arrow" for m in marks)
            r["linked"] += sum(m["step"] is not None for m in marks if m["kind"] == "label")
            r["step_text_lines"] += info["step_text_lines"]
    r["seconds"] = round(time.time() - t0, 1)
    report[g["id"]] = r
    print(g["id"], r, flush=True)
(ROOT / "reports" / "guide_ocr_drafts.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
print("TOTAL pins", sum(r["pins"] for r in report.values()), "arrows", sum(r["arrows"] for r in report.values()), "linked to a step", sum(r["linked"] for r in report.values()),
      "| step-text lines found inside pictures:", sum(r["step_text_lines"] for r in report.values()))
