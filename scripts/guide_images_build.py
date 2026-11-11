"""Render every dissection guide and crop each slide to its anatomy picture(s) (LibreOffice + pypdfium2; pptx shapes decide the crop). Without LibreOffice (or with --pictures) the embedded
pictures are used as they are. Usage: python scripts/guide_images_build.py [--only class-17] [--force] [--pictures]. Originals are only read.
Output: data/processed/guide_images/ (git-ignored) and reports/guide_images_build.json (per guide: slides cropped automatically / needing review / without a picture)."""
import argparse
import json
import sys
import time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app_api import catalog
from src import guide_images as GI
from src.ingest import guides as G
from src.modes import guide_slides as GS

ap = argparse.ArgumentParser()
ap.add_argument("--only")
ap.add_argument("--force", action="store_true")
ap.add_argument("--pictures", action="store_true")
a = ap.parse_args()
SRC = [ROOT / "data" / "raw" / "dissection_guides_revised", ROOT / "data" / "raw" / "dissection_guides"]
report = {}
for g in catalog.guides():
    if a.only and g["id"] != a.only:
        continue
    f = next((d / g["file"] for d in SRC if (d / g["file"]).exists()), None)
    if f is None:
        report[g["id"]] = {"skipped": "pptx not found"}
        print(g["id"], "pptx not found", flush=True)
        continue
    rows = GI.slide_rows(G.SLIDES_PATH, g["file"])
    stations = GS.build_stations(rows, g["entry"]["class_label"])
    by_slide = {n: st["steps"] for st in stations for n in st["slides"]}
    t = time.time()
    try:
        r = GI.build_pictures(f, g["id"], rows) if a.pictures or not GI.soffice() else GI.build_guide(f, g["id"], rows, lambda n: by_slide.get(n, []), force=True if a.force else False)
    except Exception as e:
        r = {"slides": {}, "crops": 0, "skipped": f"{type(e).__name__}: {str(e)[:160]}"}
    r["seconds"] = round(time.time() - t, 1)
    report[g["id"]] = r
    print(g["id"], r, flush=True)
(ROOT / "reports" / "guide_images_build.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
tot = {k: sum(r.get("slides", {}).get(k, 0) for r in report.values()) for k in ("auto", "review", "none")}
print("TOTAL slides: cropped automatically", tot["auto"], "| needs review", tot["review"], "| no picture", tot["none"], "| crops", sum(r.get("crops", 0) for r in report.values()))
