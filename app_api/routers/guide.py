"""Dissection guides: the list, a guide's stations, and "check what I see" (the judge of src/modes/guide_slides.py).

Stations are the same ones the Streamlit Guide uses (guide_slides.build_stations): numbered from 1 there, `index` here is that number
minus 1. Every word a student is shown comes from the slides; the judge compares the student's description with the station text only.
Lecture-notes sample mode lists the stations of one lecture (guide.build_stations) with the notes lines, fact-check handling applied.
"""
import re

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse

from app_api import catalog, config, convert, deps, guide_media
from app_api.deps import Ctx
from app_api.errors import ApiError
from app_api.schemas import BodyTipOut, CheckIn, CheckOut, ExplainIn, ExplainOut, GuideHistoryIn, GuideHistoryItem, GuideItem, Ok, Station
from src import body_type as body_mod
from src import guide_images as GI
from src import guide_marks as GM
from src import guide_store
from src import student_view as sv
from src import usage
from src.modes import guide, guide_slides as GS, qa

router = APIRouter(tags=["guide"])
VERDICT = {"yes": "correct", "partial": "partly", "no": "not_matching"}
_stations = {}


def stations_of(g):
    """Stations of one guide (cached until the slides file changes)."""
    from src.ingest import guides as G
    stamp = G.SLIDES_PATH.stat().st_mtime if G.SLIDES_PATH.exists() else 0
    key = (g["file"], stamp)
    if key not in _stations:
        _stations.clear()
        _stations[key] = GS.build_stations(GS.slides_of(g["file"]), g["entry"]["class_label"])
    return _stations[key]


def counts():
    """station count per guide file, one pass over the slides file."""
    from src.ingest import guides as G
    stamp = G.SLIDES_PATH.stat().st_mtime if G.SLIDES_PATH.exists() else 0
    hit = _stations.get(("counts", stamp))
    if hit is None:
        by_file = {}
        for g in catalog.guides():
            by_file[g["file"]] = len(stations_of(g))
        hit = _stations[("counts", stamp)] = by_file
    return hit


def need_guide(ctx, guide_id):
    g = catalog.guide_by_id(guide_id)
    if g is None:
        raise ApiError(404, "That guide was not found.")
    if g["file"] not in catalog.open_guides(ctx.allowed):
        raise ApiError(403, "That guide is not open to you. Ask your instructor.")
    return g


@router.get("/guides", response_model=list[GuideItem])
def list_guides(ctx: Ctx = Depends(deps.current)):
    open_files = catalog.open_guides(ctx.allowed)
    by_file = counts()
    return [{"id": g["id"], "class_number": g["class_number"], "title": g["title"], "region": g["region"],
             "station_count": by_file.get(g["file"], 0), "granted": g["file"] in open_files} for g in catalog.guides()]


@router.get("/guides/{guide_id}/stations", response_model=list[Station])
def guide_stations(guide_id: str, ctx: Ctx = Depends(deps.student_ctx)):
    g = need_guide(ctx, guide_id)
    store = GM.MarkStore()
    return [{"index": s["n"] - 1, "title": sv.scrub_text(s["title"])[0], "steps": [sv.scrub_text(t)[0] for t in s["steps"]],
             "slides": list(s["slides"]), "image_only": s["image_only"], "images": guide_media.station_images(g, s, store=store)} for s in stations_of(g)]


@router.get("/guides/{guide_id}/slides/{n}/crops/{k}/image")
def crop_image(guide_id: str, n: int, k: int, ctx: Ctx = Depends(deps.current)):
    return serve_crop(ctx, guide_id, n, k, False)


@router.get("/guides/{guide_id}/slides/{n}/crops/{k}/thumb")
def crop_thumb(guide_id: str, n: int, k: int, ctx: Ctx = Depends(deps.current)):
    return serve_crop(ctx, guide_id, n, k, True)


@router.get("/guides/{guide_id}/slides/{n}/original")
def original_slide(guide_id: str, n: int, ctx: Ctx = Depends(deps.instructor_ctx)):
    """The WHOLE slide (with its step text): instructors only, for "View original slide" in the editor. A student gets 403 even for a guide they may open."""
    g = need_guide(ctx, guide_id)
    path = GI.original_path(g["id"], n)
    if not path.exists():
        raise ApiError(404, "That slide has no image.")
    return FileResponse(path, media_type="image/png", headers=IMAGE_HEADERS)


IMAGE_HEADERS = {"Cache-Control": "private, max-age=3600", "X-Robots-Tag": "noindex, noimageindex", "Content-Disposition": "inline"}


def serve_crop(ctx, guide_id, n, k, thumb):
    """A cropped picture goes only to a signed-in user who may open that guide (403 otherwise; an instructor may open every guide). There is no public URL: some slides hold third-party atlas art.
    A student gets a low-confidence crop only after the instructor has marked it checked."""
    g = need_guide(ctx, guide_id)
    crop = next((c for c in GI.crops_of(g["id"], n) if c["k"] == k), None)
    if crop is None:
        raise ApiError(404, "That slide has no image.")
    if not ctx.is_instructor and crop["confidence"] != "high" and (n, k) not in GM.MarkStore().reviewed(g["id"]):
        raise ApiError(404, "That slide has no image.")
    path = GI.crop_path(g["id"], n, k, thumb)
    if not path.exists():
        raise ApiError(404, "That slide has no image.")
    return FileResponse(path, media_type="image/webp", headers=IMAGE_HEADERS)


_explained = {}


@router.post("/guides/{guide_id}/stations/{index}/explain", response_model=ExplainOut)
def explain_station(guide_id: str, index: int, body: ExplainIn, ctx: Ctx = Depends(deps.student_ctx), rt=Depends(deps.runtime)):
    """\"Explain simply\": a short AI explanation under the station's steps, from the guide and the lecture notes the student may open only. Labelled as AI."""
    from src import guide_explain as GE
    g = need_guide(ctx, guide_id)
    stations = stations_of(g)
    if not 0 <= index < len(stations):
        raise ApiError(404, "That station was not found.")
    station = stations[index]
    if station["image_only"] or not station["steps"]:
        raise ApiError(422, "This station is a picture, so there is no text to explain.")
    bt = body.body_type or ("" if ctx.preview else guide_store.GuideStore().body_type_of(ctx.owner, "guide", guide_id))
    allowed = ctx.allowed
    key = (g["file"], index, bt or "", hash(tuple(sorted(allowed))) if allowed is not None else 0)
    if key not in _explained:
        notes = GE.notes_passages(station, rt.searcher, allowed, qa.load_context())
        try:
            out, tokens = GE.explain(rt.client, rt.model, station, notes, bt)
        except Exception:
            raise ApiError(502, "The explanation could not be written just now. Please try again.")
        ctx.sessions.add_cost(ctx.token, qa.cost_of(tokens, rt.model) or 0.0)
        if out is None:
            raise ApiError(502, "The explanation could not be written safely just now. Please read the steps above.")
        srcs = [guide_source(g, station)] + [{"n": i + 2, "type": "notes", "title": "Lecture notes", "subtitle": n["breadcrumb"].split(" > ", 1)[-1], "lecture_id": convert._lecture_id(n["lecture"]),
                                              "url": None, "snippet": n["text"][:300], "retrieved_at": None, "license": None} for i, n in enumerate(notes)]
        _explained[key] = {"text": sv.scrub_text(out["text"])[0], "label": GE.LABEL, "sources": srcs}
        usage.log_event({"mode": "guide", "kind": "professor_preview" if ctx.preview else "guide_explain", "user": ctx.log_user, "lecture": g["entry"]["display_name"], "station": index + 1})
    return _explained[key]


def guide_source(g, station):
    cite = re.sub(r"^Dissection Guide,\s*", "", station["cite"])
    first = g["lecture_ids"][0] if g["lecture_ids"] else None
    return {"n": 1, "type": "guide", "title": "Dissection guide", "subtitle": cite, "lecture_id": first, "url": None,
            "snippet": sv.scrub_text(station["text"])[0], "retrieved_at": None, "license": None}


@router.post("/guides/{guide_id}/stations/{index}/check", response_model=CheckOut)
def check_station(guide_id: str, index: int, body: CheckIn, ctx: Ctx = Depends(deps.student_ctx), rt=Depends(deps.runtime)):
    g = need_guide(ctx, guide_id)
    stations = stations_of(g)
    if not 0 <= index < len(stations):
        raise ApiError(404, "That station was not found.")
    description = body.description.strip()
    if not description:
        raise ApiError(422, "Describe what you can see, then check it.")
    if len(description) > config.MAX_DESCRIPTION:
        raise ApiError(422, f"That description is {len(description):,} characters long. The limit is {config.MAX_DESCRIPTION}.")
    station = stations[index]
    if station["image_only"]:
        raise ApiError(422, f"This station is a picture (slide {station['slides'][0]}), so there is no text to compare your description with.")
    sess = GS.SlideGuideSession.open(rt.client, rt.model, g["entry"])
    sess.body_type = body.body_type or ("" if ctx.preview else guide_store.GuideStore().body_type_of(ctx.owner, "guide", guide_id))
    sess.goto(index + 1)
    turn = sess.assess(description)
    detail = turn["detail"]
    usage.log_event({"mode": "guide", "kind": "professor_preview" if ctx.preview else "guide_step",
                     "user": ctx.log_user, "lecture": g["entry"]["display_name"], "station": index + 1, "verdict": detail["verdict"],
                     "cost": turn["cost"], "tokens": turn["tokens"], **({"as_user": ctx.student["username"]} if ctx.preview else {})})
    ctx.sessions.add_cost(ctx.token, turn["cost"])
    if detail["verdict"] not in VERDICT:
        raise ApiError(502, "The check could not run just now. Please try again.")
    return {"verdict": VERDICT[detail["verdict"]], "feedback_markdown": sv.scrub_text(detail["feedback"])[0],
            "sources": [guide_source(g, station)]}


_tips = {}                       # (guide file, station, body type) -> lines; a note is the same for everyone, so it is made once per process


@router.get("/guides/{guide_id}/stations/{index}/body-tip", response_model=BodyTipOut)
def body_tip(guide_id: str, index: int, body_type: str, ctx: Ctx = Depends(deps.student_ctx), rt=Depends(deps.runtime)):
    """A short note for this station and the cadaver's body type: a line grounded in the slide text when it mentions fat, fascia, muscle or depth,
    and up to two lines labelled "General tip, not from your notes". Empty for a picture-only station or a body type with nothing to adapt to."""
    g = need_guide(ctx, guide_id)
    if body_type not in body_mod.GUIDE_CHOICES:
        raise ApiError(422, "That body type is not one of the choices.")
    stations = stations_of(g)
    if not 0 <= index < len(stations):
        raise ApiError(404, "That station was not found.")
    station = stations[index]
    if station["image_only"] or not body_mod.is_active(body_type):
        return {"body_type": body_type, "lines": []}
    key = (g["file"], index, body_type)
    if key not in _tips:
        try:
            out, usage = GS.body_tip(rt.client, rt.model, station, body_type)
        except Exception:
            raise ApiError(502, "The tip could not be written just now. Please try again.")
        ctx.sessions.add_cost(ctx.token, qa.cost_of(usage, rt.model) or 0.0)
        _tips[key] = [{"text": sv.scrub_text(l["text"])[0], "general": l["general"]} for l in out["lines"]]
    return {"body_type": body_type, "lines": _tips[key]}


# ---- lecture-notes sample mode ----

def note_steps(text):
    """Station text (with fact-check markers) -> plain lines a student may read; withheld, doubtful and corrected lines carry their neutral note."""
    steps = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•o]|\d+[.)])\s+", "", line.strip())
        if not line or line.startswith("###"):
            continue
        item = sv.clean_item(line)
        if item is None:
            continue
        note = {"reviewing": sv.NEUTRAL_REVIEW, "check": sv.CHECK_SENTENCE, "corrected": sv.corrected_sentence("")}.get(item["mark"])
        steps.append(item["text"] if not note or note in item["text"] else f"{item['text']} {note}")
    return steps


@router.get("/lectures/{lecture_id}/stations", response_model=list[Station])
def lecture_stations(lecture_id: str, ctx: Ctx = Depends(deps.student_ctx)):
    title = catalog.lecture_title(lecture_id)
    if title is None:
        raise ApiError(404, "That lecture was not found.")
    if ctx.allowed is not None and title not in ctx.allowed:
        raise ApiError(403, "That lecture is not open to you. Ask your instructor.")
    rows = sorted((s for s in guide.load_sections() if s["lecture_id"] == lecture_id), key=lambda s: s["order"])
    context = qa.load_context()
    out = []
    for st in guide.build_stations(rows):
        text, _meta = guide.station_input(st, context)
        out.append({"index": st.n - 1, "title": sv.scrub_text(st.name)[0], "steps": note_steps(text), "slides": [], "image_only": False})
    return out


# ---- history: the guide and station a student reached (sidebar "Guide history") ----

def history_title(kind, ref, ctx):
    """-> (title, station count) of a guide or lecture sample the user may open, else raises 404 / 403."""
    if kind == "guide":
        g = need_guide(ctx, ref)
        return f"Class {g['class_number']} · {g['title']}", counts().get(g["file"], 0)
    title = catalog.lecture_title(ref)
    if title is None:
        raise ApiError(404, "That lecture was not found.")
    if ctx.allowed is not None and title not in ctx.allowed:
        raise ApiError(403, "That lecture is not open to you. Ask your instructor.")
    rows = [s for s in guide.load_sections() if s["lecture_id"] == ref]
    return re.sub(r"\s+-\s+", " · ", title, count=1), len(guide.build_stations(sorted(rows, key=lambda s: s["order"])))


@router.get("/guide-history", response_model=list[GuideHistoryItem])
def guide_history(ctx: Ctx = Depends(deps.student_ctx)):
    if ctx.preview:
        return []
    return [{"id": h["id"], "kind": h["kind"], "ref": h["ref"], "title": h["title"], "station": h["station"], "count": h["count"],
             "updated_at": convert.iso(h["updated"]), "body_type": h["body_type"], "notice": h["notice"]} for h in guide_store.GuideStore().history_of(ctx.owner)]


@router.put("/guide-history", response_model=Ok)
def save_guide_history(body: GuideHistoryIn, ctx: Ctx = Depends(deps.student_ctx)):
    """Called when a student opens a station. A preview saves nothing. The guide or lecture must be open to the student."""
    title, count = history_title(body.kind, body.ref, ctx)
    if body.station >= max(count, 1):
        raise ApiError(422, "That station does not exist.")
    if not ctx.preview:
        guide_store.GuideStore().touch_history(ctx.owner, body.kind, body.ref, title, body.station, count, body.body_type)
    return {"ok": True}


@router.delete("/guide-history/{item_id:path}", response_model=Ok)
def delete_guide_history(item_id: str, ctx: Ctx = Depends(deps.student_ctx)):
    """Remove one of the student's own history items. Someone else's item is a 404."""
    if ctx.preview or not guide_store.GuideStore().delete_history(ctx.owner, item_id):
        raise ApiError(404, "That item was not found.")
    return {"ok": True}
