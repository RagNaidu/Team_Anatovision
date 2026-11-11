"""Auto-draft marks (DRAFT only, never approved) from the arrows, lines, ellipses and short text boxes in every dissection guide pptx.
Run after scripts/guide_images_build.py. Writes data/guide_annotations.db (git-ignored). Usage: python scripts/guide_autodraft.py [--only class-17]"""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_api import catalog
from src import guide_autodraft as AD
from src import guide_images as GI
from src.guide_marks import MarkStore
from src.modes import guide_slides as GS

ap = argparse.ArgumentParser()
ap.add_argument("--only")
a = ap.parse_args()
SRC = [ROOT / "data" / "raw" / "dissection_guides_revised", ROOT / "data" / "raw" / "dissection_guides"]
report = {}
for g in catalog.guides():
    if a.only and g["id"] != a.only:
        continue
    f = next((d / g["file"] for d in SRC if (d / g["file"]).exists()), None)
    if f is None:
        continue
    rows = GS.slides_of(g["file"])
    st = GS.build_stations(rows, g["entry"]["class_label"])
    crops_of = lambda n, gid=g["id"]: [{"k": c["k"], "box": c["box"]} for c in GI.crops_of(gid, n)]
    moved = MarkStore().remap_to_crops(g["id"], crops_of)                   # marks drawn before the slides were cropped move onto the pictures (outside = flagged draft)
    report[g["id"]] = {**AD.draft_guide(f, g["id"], st, crops_of), "remapped": moved["moved"], "flagged": moved["flagged"]}
    print(g["id"], report[g["id"]], flush=True)
print("total", sum(r["marks"] for r in report.values()), "marks,", sum(r["linked"] for r in report.values()), "linked to a step,", sum(r["dropped"] for r in report.values()), "dropped (outside every picture),", sum(r["remapped"] for r in report.values()), "older marks moved,", sum(r["flagged"] for r in report.values()), "flagged")
(ROOT / "reports" / "guide_autodraft.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
