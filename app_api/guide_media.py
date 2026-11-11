"""Slide images and approved marks for the API: a station's images, the instructor's annotation view, and the image cards of a chat answer.

Students only ever get APPROVED marks (guide_marks.student_marks). A slide gets an image only if it has pictures or diagrams (or the station is image-only) and a rendered file exists.
"""
import re

from src import guide_images as GI
from src import guide_marks as GM
from src.modes import guide_slides as GS

MAX_CARDS = 8
_slides = {}


def visual_slides(g):
    """{slide numbers} of this guide that have at least one cropped picture."""
    meta = GI.meta(g["id"])["slides"]
    return {int(n) for n, e in meta.items() if e.get("crops")}


def station_images(g, station, marks=None, student=True, store=None):
    """The pictures of one station (cropped slides), each with its marks. student=True: approved marks only in student-safe fields, and a low-confidence crop only once the instructor has
    marked it checked. student=False (the editor): every crop with all marks, its confidence and whether it was checked."""
    store = store or GM.MarkStore()
    reviewed = store.reviewed(g["id"])
    imgs = GI.images_for(g["id"], station["slides"], station["title"], reviewed=reviewed, student=student)
    if marks is None:
        marks = store.list(g["id"], station["slides"])
    for im in imgs:
        mine = [m for m in marks if m["slide"] == im["slide"] and m["crop"] == im["crop"]]
        im["marks"] = GM.student_marks(mine) if student else [admin_mark(m) for m in mine]
        if not student:
            im["reviewed"] = (im["slide"], im["crop"]) in reviewed
            im["original_url"] = f"/api/guides/{g['id']}/slides/{im['slide']}/original"
    return imgs


def admin_mark(m):
    return {"id": m["id"], "slide": m["slide"], "crop": m["crop"], "kind": m["kind"], "geom": m["geom"], "text": m["text"], "step": m["step"], "n": m["order"] + 1, "status": m["status"],
            "author": m["author"], "version": m["version"], "source": m["source"], "flag": m["flag"]}


# ---------------------------------------------------------------- chat answers
CITE = re.compile(r"Class\s+(\d+),\s*slides?\s+(\d+)(?:\s*[-–]\s*(\d+))?", re.I)


def parse_cite(crumb):
    """'Class 17, slides 3-8' -> (17, [3..8]); None if it is not a guide slide citation."""
    m = CITE.search(crumb or "")
    if not m:
        return None
    a, b = int(m.group(2)), int(m.group(3) or m.group(2))
    return int(m.group(1)), list(range(a, min(b, a + 40) + 1))


def is_procedural(markdown):
    return len(re.findall(r"^\s*\d+\.\s", markdown or "", re.M)) >= 2


def _step_for(text, station):
    from src.guide_autodraft import match_step, tokens
    want = tokens(text)
    best, score = None, 0.0
    for i, s in enumerate(station["steps"]):
        have = tokens(s)
        sc = len(want & have) / max(1, len(want | have)) if want else 0.0
        if sc > score:
            best, score = i, sc
    return best if score >= 0.35 else None


def chat_images(view, markdown, allowed, store=None):
    """The image cards for an answer: a procedural answer gets one card per cited guide step (at most 8), a concept answer at most one.
    allowed = the student's grants (a list) or None for no restriction; a guide that is not open gets no card. -> [{guide_id, slide, url, thumb_url, caption, alt, w, h, source_n, step, marks}]"""
    from app_api import catalog
    cards, seen = [], set()
    open_files = catalog.open_guides(allowed)
    by_class = {}
    for g in catalog.guides():
        by_class.setdefault(g["class_number"], g)
    procedural = is_procedural(markdown)
    for e in view.get("sources_list", []):
        if e.get("chunk") is None:
            continue
        src = view["sources"][e["chunk"]]
        if src["source_type"] != "dissection_guide":
            continue
        parsed = parse_cite(src.get("cite", "") + " " + src.get("crumb", ""))
        if not parsed or parsed[0] not in by_class:
            continue
        g = by_class[parsed[0]]
        if g["file"] not in open_files:
            continue
        stations = GS.build_stations(GS.slides_of(g["file"]), g["entry"]["class_label"])
        ms = store or GM.MarkStore()
        reviewed = ms.reviewed(g["id"])
        for n in parsed[1]:
            if (g["id"], n) in seen:
                continue
            st = next((s for s in stations if n in s["slides"]), None)
            ims = GI.images_for(g["id"], [n], st["title"] if st else "", reviewed=reviewed)
            if not ims:
                continue
            seen.add((g["id"], n))
            im = ims[0]
            marks = [m for m in ms.list(g["id"], [n], "approved") if m["crop"] == im["crop"]]
            step = None
            unit = view.get("cite_unit", {}).get(e["n"])
            if procedural and st is not None and unit is not None and unit < len(view.get("units", [])):
                step = _step_for(view["units"][unit]["text"], st)
                if step is not None:
                    marks = [m for m in marks if m["step"] in (None, step)]
            cards.append({**im, "guide_id": g["id"], "source_n": e["n"], "step": step, "marks": GM.student_marks(marks)})
            break                                                  # one image per cited step
        if not procedural and cards:
            break
        if len(cards) >= MAX_CARDS:
            break
    return cards[:MAX_CARDS] if procedural else cards[:1]
