"""Lectures and dissection guides as the API names them (ids), and who may open what.

  lectures()            [{"id", "title"}] in file order (from data/processed/sections.jsonl, re-read when the file changes)
  guides()              [{"id", "class_number", "title", "region", "label", "file", "entry", "lecture_ids"}] in class order
  accessible_titles(u)  the lecture titles and "Dissection Guide, Class N" labels a student may use (the same rule as the Streamlit app)

Guide ids are "class-NN" (zero-padded), or "class-NN-<title>" where two guides share a class number.
A guide's region is derived from its title with a small keyword table (the map file has no region); unknown -> "Other".
"""
import json
import re
from pathlib import Path

from src.ingest import guides as G

ROOT = Path(__file__).resolve().parents[1]
SECTIONS_PATH = ROOT / "data" / "processed" / "sections.jsonl"
_cache = {}

REGIONS = (("Back", ("back", "laminectomy", "suboccipital")),
           ("Upper limb", ("scapular", "deltoid", "pectoral", "axilla", "arm", "forearm", "hand")),
           ("Lower limb", ("gluteal", "thigh", "hip", "knee", "leg", "ankle", "foot", "popliteal")),
           ("Thorax and abdomen", ("thoracoabdominal",)),
           ("Thorax", ("pleural", "lungs", "mediastinum", "heart")),
           ("Abdomen", ("abdominal", "abdomen", "digestive")),
           ("Head and neck", ("neck", "skull", "scalp", "face", "craniectomy", "brain", "temporal", "infratemporal", "orbit", "oronasal", "pharynx")))


def _stamp(path):
    try:
        return path.stat().st_mtime
    except OSError:
        return 0


def lectures():
    stamp = _stamp(SECTIONS_PATH)
    hit = _cache.get("lectures")
    if hit and hit[0] == stamp:
        return hit[1]
    rows, seen = [], set()
    if SECTIONS_PATH.exists():
        for line in SECTIONS_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                s = json.loads(line)
                if s["lecture_title"] not in seen:
                    seen.add(s["lecture_title"])
                    rows.append({"id": s["lecture_id"], "title": s["lecture_title"]})
    _cache["lectures"] = (stamp, rows)
    return rows


def lecture_title(lecture_id):
    return next((l["title"] for l in lectures() if l["id"] == lecture_id), None)


def lecture_id_for_title(title):
    return next((l["id"] for l in lectures() if l["title"] == title), None)


def region_of(title):
    words = set(re.findall(r"[a-z]+", title.lower()))
    for name, keys in REGIONS:
        if words & set(keys):
            return name
    return "Other"


def guides():
    stamp = _stamp(G.MAP_PATH)
    hit = _cache.get("guides")
    if hit and hit[0] == stamp:
        return hit[1]
    entries = sorted(G.map_by_file().values(), key=lambda e: (e["class_number"], e["file"]))
    numbers = {}
    for e in entries:
        numbers[e["class_number"]] = numbers.get(e["class_number"], 0) + 1
    rows = []
    for e in entries:
        gid = f"class-{e['class_number']:02d}"
        if numbers[e["class_number"]] > 1:
            gid += "-" + re.sub(r"[^a-z0-9]+", "-", e["title"].lower()).strip("-")
        rows.append({"id": gid, "class_number": e["class_number"], "title": e["title"], "region": region_of(e["title"]),
                     "label": G.guide_label(e), "file": e["file"], "entry": e,
                     "lecture_ids": [x for x in (e.get("matched_lecture_id"), e.get("also_lecture_id")) if x]})
    _cache["guides"] = (stamp, rows)
    return rows


def guide_by_id(guide_id):
    return next((g for g in guides() if g["id"] == guide_id), None)


def accessible_titles(user):
    """Lecture titles and guide labels this student may use (the user's grants, as listed in the catalog)."""
    granted = set(user.get("allowed_lectures", []))
    return [t for t in [l["title"] for l in lectures()] + [g["label"] for g in guides()] if t in granted]


def all_lecture_titles():
    return [l["title"] for l in lectures()]


def open_guides(allowed_titles):
    """Guide ids a user holding these titles may open (allowed_titles None = all)."""
    return {e["file"] for e in G.accessible_guides(allowed_titles)}
